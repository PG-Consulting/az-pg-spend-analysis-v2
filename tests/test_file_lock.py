"""Tests for src/file_lock — thread-safe status.json operations."""

import json
import os
import threading
import time

import pytest
from filelock import FileLock, Timeout

from src.file_lock import read_status, write_status, update_status, locked_status


# ---------------------------------------------------------------------------
# Basic read/write
# ---------------------------------------------------------------------------


def test_write_and_read_status(tmp_path):
    """write_status creates a file, read_status reads it back correctly."""
    path = str(tmp_path / "status.json")
    write_status(path, {"status": "PENDING", "chunks": 5})
    data = read_status(path)
    assert data["status"] == "PENDING"
    assert data["chunks"] == 5


def test_write_status_overwrites(tmp_path):
    """write_status replaces previous content entirely."""
    path = str(tmp_path / "status.json")
    write_status(path, {"status": "PENDING"})
    write_status(path, {"status": "PROCESSING"})
    data = read_status(path)
    assert data["status"] == "PROCESSING"
    assert "chunks" not in data


def test_write_status_preserves_utf8(tmp_path):
    """Ensure Portuguese characters survive round-trip."""
    path = str(tmp_path / "status.json")
    write_status(path, {"status": "Não Identificado", "desc": "válvula de pressão"})
    data = read_status(path)
    assert data["status"] == "Não Identificado"
    assert data["desc"] == "válvula de pressão"


# ---------------------------------------------------------------------------
# update_status (atomic read-modify-write)
# ---------------------------------------------------------------------------


def test_update_status_merges(tmp_path):
    """update_status merges new keys into existing data."""
    path = str(tmp_path / "status.json")
    write_status(path, {"status": "PROCESSING", "chunks": 5})
    result = update_status(path, {"status": "CLASSIFIED"})
    assert result["status"] == "CLASSIFIED"
    assert result["chunks"] == 5


def test_update_status_adds_new_keys(tmp_path):
    """update_status can introduce keys not present in original."""
    path = str(tmp_path / "status.json")
    write_status(path, {"status": "PROCESSING"})
    result = update_status(path, {"error": "timeout"})
    assert result["status"] == "PROCESSING"
    assert result["error"] == "timeout"


def test_update_status_returns_merged_data(tmp_path):
    """Return value of update_status is the full merged dict."""
    path = str(tmp_path / "status.json")
    write_status(path, {"a": 1, "b": 2})
    result = update_status(path, {"b": 3, "c": 4})
    assert result == {"a": 1, "b": 3, "c": 4}


# ---------------------------------------------------------------------------
# Lock file is created alongside
# ---------------------------------------------------------------------------


def test_lock_file_created(tmp_path):
    """A .lock file is created next to the status file."""
    path = str(tmp_path / "status.json")
    write_status(path, {"x": 1})
    assert os.path.exists(path + ".lock")


# ---------------------------------------------------------------------------
# Concurrent access (stress test)
# ---------------------------------------------------------------------------


def test_concurrent_updates_no_data_loss(tmp_path):
    """Multiple threads updating the same status.json must not lose writes."""
    path = str(tmp_path / "status.json")
    write_status(path, {"counter": 0})

    num_threads = 20
    increments_per_thread = 50
    barrier = threading.Barrier(num_threads)

    def increment():
        barrier.wait()  # start all threads at the same time
        for _ in range(increments_per_thread):
            lock = FileLock(path + ".lock", timeout=10)
            with lock:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["counter"] += 1
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)

    threads = [threading.Thread(target=increment) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = read_status(path)
    assert final["counter"] == num_threads * increments_per_thread


# ---------------------------------------------------------------------------
# EACCES em CIFS (Azure File Share) tratado como "lock ocupado" — retry
# ---------------------------------------------------------------------------


class TestEaccesRetry:
    """Em CIFS (Azure File Share montado em /mount/models), fcntl.flock com
    LOCK_NB pode devolver EACCES em vez de EWOULDBLOCK quando o lock está em
    uso (POSIX permite ambos). O filelock propaga PermissionError — os helpers
    devem tratar como contenção e retentar dentro do budget de _LOCK_TIMEOUT.
    Regressão do incidente: worker morreu com [Errno 13] em read_status()."""

    def _flaky_acquire(self, fail_times):
        """Retorna um acquire que falha com EACCES nas primeiras N chamadas."""
        real_acquire = FileLock.acquire
        calls = {"n": 0}

        def acquire(lock_self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] <= fail_times:
                raise PermissionError(13, "Permission denied")
            return real_acquire(lock_self, *args, **kwargs)

        return acquire, calls

    def test_read_status_retries_on_eacces(self, tmp_path, monkeypatch):
        """PermissionError transitório na aquisição → retry → leitura OK."""
        path = str(tmp_path / "status.json")
        write_status(path, {"status": "PROCESSING"})

        acquire, calls = self._flaky_acquire(fail_times=2)
        monkeypatch.setattr(FileLock, "acquire", acquire)

        data = read_status(path)
        assert data["status"] == "PROCESSING"
        assert calls["n"] >= 3  # 2 EACCES + 1 sucesso

    def test_locked_status_retries_on_eacces(self, tmp_path, monkeypatch):
        """locked_status deve sobreviver ao EACCES e gravar o write-back."""
        path = str(tmp_path / "status.json")
        write_status(path, {"status": "PROCESSING"})

        acquire, _ = self._flaky_acquire(fail_times=2)
        monkeypatch.setattr(FileLock, "acquire", acquire)

        with locked_status(path) as data:
            data["status"] = "CLASSIFIED"

        assert read_status(path)["status"] == "CLASSIFIED"

    def test_update_status_retries_on_eacces(self, tmp_path, monkeypatch):
        """update_status (read-modify-write) também passa pelo retry."""
        path = str(tmp_path / "status.json")
        write_status(path, {"status": "PROCESSING", "chunks": 5})

        acquire, _ = self._flaky_acquire(fail_times=2)
        monkeypatch.setattr(FileLock, "acquire", acquire)

        result = update_status(path, {"status": "CLASSIFIED"})
        assert result["status"] == "CLASSIFIED"
        assert result["chunks"] == 5

    def test_persistent_eacces_raises_timeout_within_budget(
        self, tmp_path, monkeypatch
    ):
        """EACCES persistente além do budget → Timeout claro, sem travar."""
        path = str(tmp_path / "status.json")
        write_status(path, {"status": "PROCESSING"})

        monkeypatch.setattr("src.file_lock._LOCK_TIMEOUT", 0.3)

        def always_eacces(lock_self, *args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(FileLock, "acquire", always_eacces)

        start = time.monotonic()
        with pytest.raises(Timeout):
            read_status(path)
        assert time.monotonic() - start < 5  # não trava além do budget
