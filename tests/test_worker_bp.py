"""Tests for blueprints/worker_bp.py — poison queue handler."""

from src.file_lock import write_status, read_status
from src.worker_helpers import handle_poison_message


class TestHandlePoisonMessage:
    def test_marks_job_as_error(self, tmp_path, monkeypatch):
        """Poison queue handler must mark the job as ERROR."""
        monkeypatch.setattr("src.worker_helpers.get_jobs_dir", lambda: str(tmp_path))

        job_dir = tmp_path / "poison-job-123"
        job_dir.mkdir()
        status_path = str(job_dir / "status.json")
        write_status(status_path, {"status": "PROCESSING", "filename": "test.xlsx"})

        handle_poison_message("poison-job-123")

        result = read_status(status_path)
        assert result["status"] == "ERROR"
        assert "poison" in result.get("error", "").lower()

    def test_ignores_already_cancelled(self, tmp_path, monkeypatch):
        """Poison handler should not overwrite CANCELLED status."""
        monkeypatch.setattr("src.worker_helpers.get_jobs_dir", lambda: str(tmp_path))

        job_dir = tmp_path / "cancelled-job"
        job_dir.mkdir()
        status_path = str(job_dir / "status.json")
        write_status(status_path, {"status": "CANCELLED"})

        handle_poison_message("cancelled-job")

        result = read_status(status_path)
        assert result["status"] == "CANCELLED"

    def test_ignores_already_classified(self, tmp_path, monkeypatch):
        """Poison handler should not overwrite CLASSIFIED status."""
        monkeypatch.setattr("src.worker_helpers.get_jobs_dir", lambda: str(tmp_path))

        job_dir = tmp_path / "classified-job"
        job_dir.mkdir()
        status_path = str(job_dir / "status.json")
        write_status(status_path, {"status": "CLASSIFIED"})

        handle_poison_message("classified-job")

        result = read_status(status_path)
        assert result["status"] == "CLASSIFIED"

    def test_ignores_nonexistent_job(self, tmp_path, monkeypatch):
        """Poison handler should not crash for missing job."""
        monkeypatch.setattr("src.worker_helpers.get_jobs_dir", lambda: str(tmp_path))

        handle_poison_message("nonexistent-job")  # should not raise

    def test_error_contains_timestamp(self, tmp_path, monkeypatch):
        """Poison handler should record error_at timestamp."""
        monkeypatch.setattr("src.worker_helpers.get_jobs_dir", lambda: str(tmp_path))

        job_dir = tmp_path / "timed-job"
        job_dir.mkdir()
        status_path = str(job_dir / "status.json")
        write_status(status_path, {"status": "PROCESSING"})

        handle_poison_message("timed-job")

        result = read_status(status_path)
        assert "error_at" in result
        assert "T" in result["error_at"]  # ISO format
