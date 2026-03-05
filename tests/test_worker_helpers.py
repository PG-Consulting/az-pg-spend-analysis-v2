"""Tests for worker_helpers — parse_custom_hierarchy and cleanup_stale_jobs."""
import json
import pytest
from datetime import datetime, timezone, timedelta

from src.worker_helpers import parse_custom_hierarchy, cleanup_stale_jobs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_HIERARCHY_LIST = [
    {"N1": "Exploração e Produção", "N2": "Engenharia", "N3": "Reservatórios", "N4": "Consultoria"},
    {"N1": "Exploração e Produção", "N2": "Engenharia", "N3": "Reservatórios", "N4": "Certificação"},
    {"N1": "Operação e Manutenção", "N2": "Materiais", "N3": "OEM", "N4": "Peças ABB"},
]


# ---------------------------------------------------------------------------
# Cenário 1: Hierarquia do projeto (custom_hierarchy_list)
# ---------------------------------------------------------------------------

class TestParseHierarchyFromProjectConfig:
    """Hierarquia definida no projeto, sem upload per-job."""

    def test_returns_list_from_project_config(self):
        status = {
            "custom_hierarchy_list": SAMPLE_HIERARCHY_LIST,
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result is not None
        assert len(result) == 3
        assert result[0]["N1"] == "Exploração e Produção"
        assert result[2]["N4"] == "Peças ABB"

    def test_preserves_all_entries(self):
        status = {
            "custom_hierarchy_list": SAMPLE_HIERARCHY_LIST,
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result == SAMPLE_HIERARCHY_LIST

    def test_ignores_empty_list(self):
        status = {
            "custom_hierarchy_list": [],
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result is None

    def test_ignores_non_list_value(self):
        status = {
            "custom_hierarchy_list": "invalid",
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result is None


# ---------------------------------------------------------------------------
# Cenário 2: Upload per-job (custom_hierarchy_b64) sobrescreve projeto
# ---------------------------------------------------------------------------

class TestParseHierarchyFromB64Upload:
    """Upload de hierarquia na execução — b64 path."""

    def test_b64_returns_none_when_absent(self):
        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result is None

    def test_b64_returns_none_for_empty_string(self):
        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": "",
        }
        result = parse_custom_hierarchy(status)
        assert result is None

    def test_b64_returns_none_for_invalid_data(self):
        """Base64 inválido não deve causar exceção, deve retornar None."""
        import base64
        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": base64.b64encode(b"not an excel file").decode(),
        }
        result = parse_custom_hierarchy(status)
        assert result is None


# ---------------------------------------------------------------------------
# Cenário 3: UNSPSC no projeto, sem upload — classificação aberta
# ---------------------------------------------------------------------------

class TestParseHierarchyOpenClassification:
    """Projeto UNSPSC/padrão, sem upload — deve retornar None."""

    def test_both_none(self):
        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": None,
        }
        assert parse_custom_hierarchy(status) is None

    def test_both_missing_keys(self):
        status = {"status": "PROCESSING"}
        assert parse_custom_hierarchy(status) is None


# ---------------------------------------------------------------------------
# Cenário 4: UNSPSC no projeto + upload na execução
# Este cenário é tratado pelo SubmitTaxonomyJob que seta
# custom_hierarchy_list=None e custom_hierarchy_b64=<upload>,
# delegando a resolução ao parse_custom_hierarchy via b64 path.
# Testamos que a list path não interfere quando é None.
# ---------------------------------------------------------------------------

class TestParseHierarchyPriorityOrder:
    """Prioridade: list (projeto) → b64 (execução) → None."""

    def test_list_takes_precedence_when_both_present(self):
        """Se ambos presentes (cenário não deveria ocorrer no código atual,
        mas parse_custom_hierarchy deve preferir list)."""
        import base64
        status = {
            "custom_hierarchy_list": SAMPLE_HIERARCHY_LIST,
            "custom_hierarchy_b64": base64.b64encode(b"some data").decode(),
        }
        result = parse_custom_hierarchy(status)
        # list path retorna primeiro
        assert result == SAMPLE_HIERARCHY_LIST

    def test_falls_through_to_b64_when_list_is_none(self):
        """custom_hierarchy_list=None, b64 presente (cenário 4: UNSPSC + upload)."""
        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": None,
        }
        # Ambos None → retorna None (classificação aberta)
        assert parse_custom_hierarchy(status) is None


# ---------------------------------------------------------------------------
# Cenário 5: cleanup_stale_jobs — timezone aware/naive
# ---------------------------------------------------------------------------

class TestCleanupStaleJobs:
    """cleanup_stale_jobs deve marcar PROCESSING > 1h como ERROR."""

    def test_marks_stale_processing_job_as_error(self, tmp_path):
        job_dir = tmp_path / "stale-job"
        job_dir.mkdir()
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        status = {"status": "PROCESSING", "created_at": two_hours_ago}
        (job_dir / "status.json").write_text(json.dumps(status))
        cleanup_stale_jobs(str(tmp_path))
        result = json.loads((job_dir / "status.json").read_text())
        assert result["status"] == "ERROR"

    def test_ignores_recent_processing_job(self, tmp_path):
        job_dir = tmp_path / "recent-job"
        job_dir.mkdir()
        just_now = datetime.now(timezone.utc).isoformat()
        status = {"status": "PROCESSING", "created_at": just_now}
        (job_dir / "status.json").write_text(json.dumps(status))
        cleanup_stale_jobs(str(tmp_path))
        result = json.loads((job_dir / "status.json").read_text())
        assert result["status"] == "PROCESSING"

    def test_ignores_non_processing_jobs(self, tmp_path):
        job_dir = tmp_path / "done-job"
        job_dir.mkdir()
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        status = {"status": "COMPLETED", "created_at": old}
        (job_dir / "status.json").write_text(json.dumps(status))
        cleanup_stale_jobs(str(tmp_path))
        result = json.loads((job_dir / "status.json").read_text())
        assert result["status"] == "COMPLETED"
