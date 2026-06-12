"""Tests for blueprints/worker_bp.py — poison queue handler."""

import json
from datetime import datetime, timezone, timedelta

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


class TestJobRetention:
    """CleanupStaleJobs deve deletar jobs antigos COMPLETED/ERROR."""

    def test_deletes_completed_job_older_than_30_days(self, tmp_path):
        """Job COMPLETED com mais de 30 dias deve ser deletado."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "old-completed"
        job_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        status = {"status": "COMPLETED", "created_at": old_date}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 1
        assert not job_dir.exists()

    def test_keeps_completed_job_within_30_days(self, tmp_path):
        """Job COMPLETED com menos de 30 dias NÃO deve ser deletado."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "recent-completed"
        job_dir.mkdir()
        recent_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        status = {"status": "COMPLETED", "created_at": recent_date}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 0
        assert job_dir.exists()

    def test_keeps_processing_job_even_if_old(self, tmp_path):
        """Job PROCESSING NÃO deve ser deletado pela retenção."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "old-processing"
        job_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        status = {"status": "PROCESSING", "created_at": old_date}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 0
        assert job_dir.exists()

    def test_deletes_error_job_older_than_30_days(self, tmp_path):
        """Job ERROR com mais de 30 dias deve ser deletado."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "old-error"
        job_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        status = {"status": "ERROR", "created_at": old_date}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 1
        assert not job_dir.exists()

    def test_deletes_legacy_job_with_naive_created_at(self, tmp_path, caplog):
        """Job legado (era datetime.utcnow) tem created_at NAIVE — deve ser deletado.

        Regressão de produção: `datetime.now(timezone.utc) - created_dt` com
        created_dt naive levanta TypeError ("can't subtract offset-naive and
        offset-aware datetimes"); o except logava e pulava → jobs legados
        terminais NUNCA eram deletados e o App Insights era spammado a cada hora.
        """
        import logging

        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "legacy-naive-completed"
        job_dir.mkdir()
        # Timestamp naive (sem offset), como os gerados por datetime.utcnow()
        old_naive = (
            (datetime.now(timezone.utc) - timedelta(days=35))
            .replace(tzinfo=None)
            .isoformat()
        )
        status = {"status": "COMPLETED", "created_at": old_naive}
        (job_dir / "status.json").write_text(json.dumps(status))

        with caplog.at_level(logging.ERROR, logger="src.worker_helpers"):
            deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)

        assert deleted == 1
        assert not job_dir.exists()
        # Nenhum spam "[Retention] Error checking job ..." pode ser logado
        retention_errors = [
            r.message for r in caplog.records if "[Retention] Error" in r.message
        ]
        assert retention_errors == []

    def test_keeps_recent_legacy_job_with_naive_created_at(self, tmp_path):
        """Job legado naive recente deve ser mantido (UTC assumido, não local)."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "legacy-naive-recent"
        job_dir.mkdir()
        recent_naive = (
            (datetime.now(timezone.utc) - timedelta(days=5))
            .replace(tzinfo=None)
            .isoformat()
        )
        status = {"status": "COMPLETED", "created_at": recent_naive}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 0
        assert job_dir.exists()

    def test_keeps_old_processing_legacy_job_with_naive_created_at(self, tmp_path):
        """Job legado naive em estado não-terminal nunca é deletado."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "legacy-naive-processing"
        job_dir.mkdir()
        old_naive = (
            (datetime.now(timezone.utc) - timedelta(days=90))
            .replace(tzinfo=None)
            .isoformat()
        )
        status = {"status": "PROCESSING", "created_at": old_naive}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 0
        assert job_dir.exists()
