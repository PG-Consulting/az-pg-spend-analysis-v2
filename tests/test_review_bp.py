"""Tests for blueprints/review_bp.py — jobId validation.

Uses the same azure.functions mock pattern as test_api_helpers.py.
"""
import json
import sys
import types
import pytest
from unittest.mock import MagicMock

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
