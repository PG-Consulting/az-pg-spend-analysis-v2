"""Thread-safe file operations for status.json.

Uses filelock to prevent race conditions when the worker (queue trigger)
and HTTP endpoints read/write status.json concurrently.

All writes use write-to-temp-then-rename for crash safety:
if the process dies during json.dump, the original file is untouched.
"""

import json
import logging
import os
from contextlib import contextmanager
from typing import Dict, Any

from filelock import FileLock

logger = logging.getLogger(__name__)

# Default timeout for acquiring the lock (seconds).
_LOCK_TIMEOUT = 10


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
    lock = FileLock(status_path + ".lock", timeout=_LOCK_TIMEOUT)
    with lock:
        with open(status_path, "r", encoding="utf-8") as f:
            return json.load(f)


def write_status(status_path: str, data: Dict[str, Any]) -> None:
    """Write *data* to status.json under a file lock (full overwrite)."""
    lock = FileLock(status_path + ".lock", timeout=_LOCK_TIMEOUT)
    with lock:
        _atomic_write(status_path, data)


def update_status(status_path: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Atomic read-modify-write: merge *updates* into the existing status.json.

    Returns the merged dict after writing.
    """
    lock = FileLock(status_path + ".lock", timeout=_LOCK_TIMEOUT)
    with lock:
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
    lock = FileLock(status_path + ".lock", timeout=_LOCK_TIMEOUT)
    with lock:
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        yield data
        _atomic_write(status_path, data)
