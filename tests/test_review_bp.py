"""Tests for blueprints/review_bp.py — jobId validation and approve flow.

Uses the same azure.functions mock pattern as test_api_helpers.py.
"""
import json
import os
import sys
import types
import pytest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Mock azure.functions before importing blueprints
# ---------------------------------------------------------------------------
_mock_azure = types.ModuleType("azure")
_mock_func = types.ModuleType("azure.functions")


class _MockHttpResponse:
    """Minimal mock of azure.functions.HttpResponse."""
    def __init__(self, body=None, status_code=200, mimetype=None, headers=None):
        self._body = body.encode("utf-8") if isinstance(body, str) else (body or b"")
        self.status_code = status_code
        self.mimetype = mimetype
        self.headers = headers or {}

    def get_body(self):
        return self._body


class _MockHttpRequest:
    """Minimal mock of azure.functions.HttpRequest."""
    pass


class _MockAuthLevel:
    ANONYMOUS = "ANONYMOUS"
    FUNCTION = "FUNCTION"
    ADMIN = "ADMIN"


class _MockBlueprint:
    def route(self, *a, **kw):
        def decorator(fn):
            return fn
        return decorator


_mock_func.HttpResponse = _MockHttpResponse
_mock_func.HttpRequest = _MockHttpRequest
_mock_func.AuthLevel = _MockAuthLevel
_mock_func.Blueprint = _MockBlueprint
_mock_azure.functions = _mock_func
sys.modules["azure"] = _mock_azure
sys.modules["azure.functions"] = _mock_func

# Now safe to import
from src.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReclassifyItemsJobIdValidation:
    """ReclassifyItems deve rejeitar jobId vazio."""

    def test_empty_jobid_raises_validation_error(self):
        """Quando jobId e string vazia, deve levantar ValidationError."""
        from blueprints.review_bp import reclassify_items_endpoint

        req = MagicMock()
        req.get_json.return_value = {
            "jobId": "",
            "projectId": "test-project",
            "items": [{"index": 0, "description": "Parafuso M8"}],
            "instruction": "Reclassificar",
        }

        response = reclassify_items_endpoint(req)
        assert response.status_code == 400
        body = json.loads(response.get_body())
        assert "jobid" in body.get("error", "").lower() or "required" in body.get("error", "").lower()

    def test_missing_jobid_raises_validation_error(self):
        """Quando jobId nao esta no body, default e '' — deve levantar ValidationError."""
        from blueprints.review_bp import reclassify_items_endpoint

        req = MagicMock()
        req.get_json.return_value = {
            "projectId": "test-project",
            "items": [{"index": 0, "description": "Parafuso M8"}],
            "instruction": "Reclassificar",
        }

        response = reclassify_items_endpoint(req)
        assert response.status_code == 400


class TestApproveClassificationsJobIdValidation:
    """ApproveClassifications deve rejeitar jobId vazio."""

    def test_empty_jobid_raises_validation_error(self):
        """Quando jobId e string vazia, deve levantar ValidationError."""
        from blueprints.review_bp import approve_classifications_endpoint

        req = MagicMock()
        req.get_json.return_value = {
            "jobId": "",
            "projectId": "test-project",
            "decisions": [],
        }

        response = approve_classifications_endpoint(req)
        assert response.status_code == 400
        body = json.loads(response.get_body())
        assert "jobid" in body.get("error", "").lower() or "required" in body.get("error", "").lower()


class TestApproveClassificationsBase64Separation:
    """ApproveClassifications deve salvar Excel base64 em arquivo separado, não no status.json."""

    def _setup_job_dir(self, tmp_path, job_id="test-job-123"):
        """Cria diretório de job com status.json e result.json mínimos."""
        job_dir = tmp_path / "taxonomy_jobs" / job_id
        job_dir.mkdir(parents=True)

        status_data = {
            "job_id": job_id,
            "status": "CLASSIFIED",
            "sector": "teste",
            "filename": "base_teste.xlsx",
            "id_column": "SKU",
            "desc_column": "Descricao",
            "total_rows": 2,
            "total_chunks": 1,
            "processed_chunks": 1,
        }
        with open(job_dir / "status.json", "w", encoding="utf-8") as f:
            json.dump(status_data, f)

        result_data = {
            "items": [
                {"SKU": "001", "Descricao": "Parafuso M8", "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Paraf", "source": "LLM (Batch)", "confidence": 0.9},
                {"SKU": "002", "Descricao": "Porca M10", "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Porcas", "source": "LLM (Batch)", "confidence": 0.85},
            ]
        }
        with open(job_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(result_data, f)

        return job_dir

    @patch("blueprints.review_bp.KnowledgeBase")
    def test_base64_not_in_status_json(self, mock_kb_class, tmp_path, monkeypatch):
        """Após ApproveClassifications, status.json NÃO deve conter approved_file_content_base64."""
        job_id = "test-b64-sep"
        job_dir = self._setup_job_dir(tmp_path, job_id)

        monkeypatch.setattr("blueprints.review_bp.get_models_dir", lambda: str(tmp_path))
        monkeypatch.setattr("blueprints.review_bp.get_jobs_dir", lambda: str(tmp_path / "taxonomy_jobs"))

        from blueprints.review_bp import approve_classifications_endpoint

        req = MagicMock()
        req.get_json.return_value = {
            "jobId": job_id,
            "projectId": "",
            "decisions": [
                {"index": 0, "description": "Parafuso M8", "decision": "approved",
                 "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Paraf",
                 "confidence": 0.9, "source": "LLM (Batch)"},
            ],
        }

        response = approve_classifications_endpoint(req)
        assert response.status_code == 200

        # Verificar que status.json NÃO contém o base64
        with open(job_dir / "status.json", "r", encoding="utf-8") as f:
            status_data = json.load(f)
        assert "approved_file_content_base64" not in status_data

    @patch("blueprints.review_bp.KnowledgeBase")
    def test_base64_saved_in_separate_file(self, mock_kb_class, tmp_path, monkeypatch):
        """Após ApproveClassifications, deve existir approved_result_b64.txt com o conteúdo base64."""
        job_id = "test-b64-file"
        job_dir = self._setup_job_dir(tmp_path, job_id)

        monkeypatch.setattr("blueprints.review_bp.get_models_dir", lambda: str(tmp_path))
        monkeypatch.setattr("blueprints.review_bp.get_jobs_dir", lambda: str(tmp_path / "taxonomy_jobs"))

        from blueprints.review_bp import approve_classifications_endpoint

        req = MagicMock()
        req.get_json.return_value = {
            "jobId": job_id,
            "projectId": "",
            "decisions": [
                {"index": 0, "description": "Parafuso M8", "decision": "approved",
                 "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Paraf",
                 "confidence": 0.9, "source": "LLM (Batch)"},
            ],
        }

        response = approve_classifications_endpoint(req)
        assert response.status_code == 200

        # Verificar que o arquivo separado existe
        b64_path = job_dir / "approved_result_b64.txt"
        assert b64_path.exists(), "approved_result_b64.txt deve existir"

        # Verificar que o conteúdo é base64 válido (decodifica sem erro)
        import base64
        content = b64_path.read_text(encoding="utf-8")
        assert len(content) > 0
        base64.b64decode(content)  # Não deve levantar exceção

    @patch("blueprints.review_bp.KnowledgeBase")
    def test_response_still_contains_base64(self, mock_kb_class, tmp_path, monkeypatch):
        """A resposta HTTP ainda deve conter file_content_base64 para o frontend."""
        job_id = "test-b64-resp"
        job_dir = self._setup_job_dir(tmp_path, job_id)

        monkeypatch.setattr("blueprints.review_bp.get_models_dir", lambda: str(tmp_path))
        monkeypatch.setattr("blueprints.review_bp.get_jobs_dir", lambda: str(tmp_path / "taxonomy_jobs"))

        from blueprints.review_bp import approve_classifications_endpoint

        req = MagicMock()
        req.get_json.return_value = {
            "jobId": job_id,
            "projectId": "",
            "decisions": [
                {"index": 0, "description": "Parafuso M8", "decision": "approved",
                 "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Paraf",
                 "confidence": 0.9, "source": "LLM (Batch)"},
            ],
        }

        response = approve_classifications_endpoint(req)
        body = json.loads(response.get_body())
        assert "file_content_base64" in body
        assert body["file_content_base64"] is not None
        assert len(body["file_content_base64"]) > 0


class TestApproveClassificationsExtraColumns:
    """ApproveClassifications deve incluir colunas extras (ex: Fornecedor) no Excel de saída."""

    def _setup_job_dir(self, tmp_path, job_id="test-extra-cols"):
        job_dir = tmp_path / "taxonomy_jobs" / job_id
        job_dir.mkdir(parents=True)

        status_data = {
            "job_id": job_id,
            "status": "CLASSIFIED",
            "sector": "teste",
            "filename": "base_teste.xlsx",
            "id_column": "SKU",
            "desc_column": "Descricao",
            "extra_columns": ["Fornecedor"],
            "total_rows": 2,
            "total_chunks": 1,
            "processed_chunks": 1,
        }
        with open(job_dir / "status.json", "w", encoding="utf-8") as f:
            json.dump(status_data, f)

        result_data = {
            "items": [
                {"SKU": "001", "Descricao": "Parafuso M8", "Fornecedor": "ABC Ltda",
                 "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Paraf",
                 "source": "LLM (Batch)", "confidence": 0.9},
                {"SKU": "002", "Descricao": "Porca M10", "Fornecedor": "XYZ SA",
                 "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Porcas",
                 "source": "LLM (Batch)", "confidence": 0.85},
            ]
        }
        with open(job_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(result_data, f)

        return job_dir

    @patch("blueprints.review_bp.KnowledgeBase")
    def test_extra_columns_in_approved_excel(self, mock_kb_class, tmp_path, monkeypatch):
        """Excel de saída deve conter coluna Fornecedor entre Descrição e N1."""
        import base64

        job_id = "test-extra-cols"
        self._setup_job_dir(tmp_path, job_id)

        monkeypatch.setattr("blueprints.review_bp.get_models_dir", lambda: str(tmp_path))
        monkeypatch.setattr("blueprints.review_bp.get_jobs_dir", lambda: str(tmp_path / "taxonomy_jobs"))

        from blueprints.review_bp import approve_classifications_endpoint

        req = MagicMock()
        req.get_json.return_value = {
            "jobId": job_id,
            "projectId": "",
            "decisions": [
                {"index": 0, "description": "Parafuso M8", "decision": "approved",
                 "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Paraf",
                 "confidence": 0.9, "source": "LLM (Batch)"},
                {"index": 1, "description": "Porca M10", "decision": "approved",
                 "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Porcas",
                 "confidence": 0.85, "source": "LLM (Batch)"},
            ],
        }

        response = approve_classifications_endpoint(req)
        assert response.status_code == 200

        body = json.loads(response.get_body())
        excel_bytes = base64.b64decode(body["file_content_base64"])

        import pandas as pd
        import io
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Classificados")

        assert "Fornecedor" in df.columns
        assert list(df.columns) == ["SKU", "Descrição", "Fornecedor", "N1", "N2", "N3", "N4", "Fonte"]
        assert df.iloc[0]["Fornecedor"] == "ABC Ltda"
        assert df.iloc[1]["Fornecedor"] == "XYZ SA"

    @patch("blueprints.review_bp.KnowledgeBase")
    def test_no_extra_columns_when_absent(self, mock_kb_class, tmp_path, monkeypatch):
        """Sem extra_columns no status, Excel deve ter formato padrão."""
        job_id = "test-no-extra"
        job_dir = tmp_path / "taxonomy_jobs" / job_id
        job_dir.mkdir(parents=True)

        status_data = {
            "job_id": job_id, "status": "CLASSIFIED", "sector": "teste",
            "filename": "base.xlsx", "id_column": "SKU", "desc_column": "Descricao",
            "total_rows": 1, "total_chunks": 1, "processed_chunks": 1,
        }
        with open(job_dir / "status.json", "w", encoding="utf-8") as f:
            json.dump(status_data, f)

        result_data = {
            "items": [
                {"SKU": "001", "Descricao": "Parafuso M8",
                 "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Paraf",
                 "source": "LLM (Batch)", "confidence": 0.9},
            ]
        }
        with open(job_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(result_data, f)

        monkeypatch.setattr("blueprints.review_bp.get_models_dir", lambda: str(tmp_path))
        monkeypatch.setattr("blueprints.review_bp.get_jobs_dir", lambda: str(tmp_path / "taxonomy_jobs"))

        from blueprints.review_bp import approve_classifications_endpoint

        req = MagicMock()
        req.get_json.return_value = {
            "jobId": job_id, "projectId": "",
            "decisions": [
                {"index": 0, "description": "Parafuso M8", "decision": "approved",
                 "N1": "Mat", "N2": "Comp", "N3": "Fix", "N4": "Paraf",
                 "confidence": 0.9, "source": "LLM (Batch)"},
            ],
        }

        response = approve_classifications_endpoint(req)
        body = json.loads(response.get_body())

        import base64, pandas as pd, io
        df = pd.read_excel(io.BytesIO(base64.b64decode(body["file_content_base64"])), sheet_name="Classificados")
        assert "Fornecedor" not in df.columns
        assert list(df.columns) == ["SKU", "Descrição", "N1", "N2", "N3", "N4", "Fonte"]


# ---------------------------------------------------------------------------
# Lógica de filtragem de itens incompletos para KB (ApproveClassifications)
# ---------------------------------------------------------------------------

class TestApproveLogic:
    """Testa a lógica de filtragem de itens incompletos antes de alimentar a KB."""

    _incomplete = {"", "Não Identificado"}

    def _should_skip(self, decision: dict) -> bool:
        """Reproduz a lógica de filtragem usada em ApproveClassifications."""
        return any(
            str(decision.get(lvl, "")).strip() in self._incomplete
            for lvl in ("N1", "N2", "N3", "N4")
        )

    def test_incomplete_items_excluded_from_kb(self):
        """Items with 'Não Identificado' should not be added to KB."""
        decision = {"N1": "Não Identificado", "N2": "Test", "N3": "Test", "N4": "Test"}
        assert self._should_skip(decision) is True

    def test_complete_items_included_in_kb(self):
        """Items fully classified should be included in KB."""
        decision = {"N1": "MRO", "N2": "Materiais", "N3": "Hidráulicos", "N4": "Tubos"}
        assert self._should_skip(decision) is False

    def test_empty_n4_excluded_from_kb(self):
        """Items with empty N4 should not be added to KB."""
        decision = {"N1": "MRO", "N2": "Materiais", "N3": "Hidráulicos", "N4": ""}
        assert self._should_skip(decision) is True

    def test_empty_n1_excluded_from_kb(self):
        """Items with empty N1 should not be added to KB."""
        decision = {"N1": "", "N2": "Materiais", "N3": "Hidráulicos", "N4": "Tubos"}
        assert self._should_skip(decision) is True

    def test_whitespace_only_excluded_from_kb(self):
        """Items where a level is only whitespace should be excluded."""
        decision = {"N1": "MRO", "N2": "  ", "N3": "Hidráulicos", "N4": "Tubos"}
        assert self._should_skip(decision) is True

    def test_missing_key_excluded_from_kb(self):
        """Items missing a level key entirely should be excluded (defaults to '')."""
        decision = {"N1": "MRO", "N2": "Materiais", "N3": "Hidráulicos"}
        assert self._should_skip(decision) is True

    def test_all_nao_identificado_excluded(self):
        """Items where all levels are 'Não Identificado' should be excluded."""
        decision = {
            "N1": "Não Identificado",
            "N2": "Não Identificado",
            "N3": "Não Identificado",
            "N4": "Não Identificado",
        }
        assert self._should_skip(decision) is True

    def test_multiple_complete_items(self):
        """All complete items should pass the filter."""
        decisions = [
            {"N1": "Serviços", "N2": "Consultoria", "N3": "TI", "N4": "SAP"},
            {"N1": "MRO", "N2": "Elétricos", "N3": "Cabos", "N4": "Cabo 10mm"},
            {"N1": "Capex", "N2": "Equipamentos", "N3": "Bombas", "N4": "Centrífuga"},
        ]
        for d in decisions:
            assert self._should_skip(d) is False, f"Should not skip: {d}"
