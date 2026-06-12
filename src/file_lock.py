"""Thread-safe file operations for status.json.

Uses filelock to prevent race conditions when the worker (queue trigger)
and HTTP endpoints read/write status.json concurrently.

All writes use write-to-temp-then-rename for crash safety:
if the process dies during json.dump, the original file is untouched.
"""

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Dict, Any

from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)

# Default timeout for acquiring the lock (seconds).
_LOCK_TIMEOUT = 10
# Per-attempt acquire timeout inside the retry loop (seconds).
_ACQUIRE_POLL_SECONDS = 0.5
# Backoff after an EACCES treated as "lock busy" (seconds).
_EACCES_RETRY_DELAY = 0.1


@contextmanager
def _acquire_lock(status_path: str):
    """Acquire the .lock file tolerating EACCES as "lock busy" (CIFS quirk).

    On the CIFS-mounted Azure File Share (/mount/models), fcntl.flock with
    LOCK_NB may fail with EACCES instead of EWOULDBLOCK when the lock is held
    (POSIX allows "EACCES or EAGAIN"). filelock propagates that as a hard
    PermissionError — here we treat it as contention: retry with a short
    backoff within the _LOCK_TIMEOUT budget. If the budget is exhausted,
    raise filelock.Timeout (same behavior as a regular lock timeout).
    """
    lock = FileLock(status_path + ".lock")
    deadline = time.monotonic() + _LOCK_TIMEOUT
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Timeout(lock.lock_file)
        try:
            lock.acquire(timeout=min(_ACQUIRE_POLL_SECONDS, remaining))
            break
        except Timeout:
            continue  # lock ocupado "normal" — loop re-checa o budget
        except PermissionError as e:
            # EACCES em CIFS = lock ocupado, não falta de permissão real.
            logger.warning(
                "Lock %s: PermissionError (EACCES) tratado como lock ocupado "
                "(CIFS/Azure File Share) — retry: %s",
                lock.lock_file,
                e,
            )
            time.sleep(min(_EACCES_RETRY_DELAY, max(remaining, 0.0)))
    try:
        yield
    finally:
        lock.release()


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    """Write JSON to a temp file then atomically rename over the target."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp_path, path)


def read_status(status_path: str) -> Dict[str, Any]:
    """Read status.json under a file lock.

    Returns the parsed JSON dict.
    """
    with _acquire_lock(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            return json.load(f)


def write_status(status_path: str, data: Dict[str, Any]) -> None:
    """Write *data* to status.json under a file lock (full overwrite)."""
    with _acquire_lock(status_path):
        _atomic_write(status_path, data)


def update_status(status_path: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Atomic read-modify-write: merge *updates* into the existing status.json.

    Returns the merged dict after writing.
    """
    with _acquire_lock(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.update(updates)
        _atomic_write(status_path, data)
    return data


@contextmanager
def locked_status(status_path: str):
    """Context manager for atomic read-modify-write on status.json.

    Usage:
        with locked_status(path) as data:
            data["status"] = "CLASSIFIED"
        # Automatically written back on exit
    """
    with _acquire_lock(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        yield data
        _atomic_write(status_path, data)
