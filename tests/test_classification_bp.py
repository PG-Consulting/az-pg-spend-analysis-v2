"""Tests for blueprints/classification_bp.py — orphan directory cleanup on parse failure.

Uses the same azure.functions mock pattern as test_api_helpers.py.
"""
import json
import os
import sys
import types
import pytest
from unittest.mock import MagicMock, patch
import base64

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


class _MockAuthLevel:
    ANONYMOUS = "ANONYMOUS"


class _MockBlueprint:
    def route(self, *a, **kw):
        def decorator(fn):
            return fn
        return decorator


_mock_func.HttpResponse = _MockHttpResponse
_mock_func.HttpRequest = MagicMock
_mock_func.AuthLevel = _MockAuthLevel
_mock_func.Blueprint = _MockBlueprint
_mock_azure.functions = _mock_func
sys.modules["azure"] = _mock_azure
sys.modules["azure.functions"] = _mock_func


class TestOrphanDirectoryCleanup:
    """Quando o parse do arquivo falha, o diretorio do job deve ser removido."""

    def test_orphan_dir_removed_on_parse_failure(self, tmp_path, monkeypatch):
        """Se parse Excel/CSV falha em todas as 3 tentativas, o diretorio criado deve ser limpo."""
        jobs_dir = str(tmp_path / "taxonomy_jobs")
        os.makedirs(jobs_dir, exist_ok=True)

        # Patch where the function is used (in the blueprint module)
        monkeypatch.setattr("blueprints.classification_bp.get_jobs_dir", lambda: jobs_dir)
        monkeypatch.setattr("blueprints.classification_bp.get_models_dir", lambda: str(tmp_path))

        from blueprints.classification_bp import SubmitTaxonomyJob

        # Create binary content that fails BOTH Excel and CSV parse
        # Pure binary noise — not parseable as Excel or CSV
        garbage = bytes(range(256)) * 4
        invalid_content = base64.b64encode(garbage).decode()

        req = MagicMock()
        req.method = "POST"
        req.get_json.return_value = {
            "fileContent": invalid_content,
            "sector": "teste",
            "originalFilename": "bad_file.bin",
        }

        response = SubmitTaxonomyJob(req)

        # Should return 400 (ValidationError) — not 500
        assert response.status_code == 400

        # The orphan directory should have been cleaned up
        remaining = os.listdir(jobs_dir)
        assert len(remaining) == 0, f"Orphan directory still exists: {remaining}"

    def test_valid_csv_does_not_trigger_cleanup(self, tmp_path, monkeypatch):
        """Arquivo CSV valido nao deve disparar cleanup."""
        import csv
        import io

        jobs_dir = str(tmp_path / "taxonomy_jobs")
        os.makedirs(jobs_dir, exist_ok=True)
        monkeypatch.setattr("blueprints.classification_bp.get_jobs_dir", lambda: jobs_dir)
        monkeypatch.setattr("blueprints.classification_bp.get_models_dir", lambda: str(tmp_path))

        from blueprints.classification_bp import SubmitTaxonomyJob

        # Create valid CSV content
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(["SKU", "Descricao"])
        writer.writerow(["001", "Parafuso M8"])
        writer.writerow(["002", "Porca M10"])
        csv_b64 = base64.b64encode(buf.getvalue().encode("utf-8")).decode()

        req = MagicMock()
        req.method = "POST"
        req.get_json.return_value = {
            "fileContent": csv_b64,
            "sector": "teste",
            "originalFilename": "items.csv",
        }

        response = SubmitTaxonomyJob(req)

        # Should succeed with 202
        assert response.status_code == 202

        # Job directory should exist
        remaining = os.listdir(jobs_dir)
        assert len(remaining) == 1
