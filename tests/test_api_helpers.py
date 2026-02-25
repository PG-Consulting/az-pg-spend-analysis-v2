"""Tests for src/api_helpers.py — json_response, error_response, handle_errors."""
import json
import sys
import types
import pytest

# Mock azure.functions before importing api_helpers
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


_mock_func.HttpResponse = _MockHttpResponse
_mock_azure.functions = _mock_func
sys.modules.setdefault("azure", _mock_azure)
sys.modules.setdefault("azure.functions", _mock_func)

from src.api_helpers import json_response, error_response, options_response, handle_errors
from src.exceptions import (
    SpendAnalysisError,
    NotFoundError,
    ValidationError,
    ConflictError,
    ExternalServiceError,
)


class TestJsonResponse:
    def test_basic_dict(self):
        resp = json_response({"key": "value"})
        assert resp.status_code == 200
        assert json.loads(resp.get_body()) == {"key": "value"}
        assert resp.mimetype == "application/json"

    def test_custom_status_code(self):
        resp = json_response({"created": True}, status_code=201)
        assert resp.status_code == 201

    def test_handles_nan(self):
        resp = json_response({"value": float("nan")})
        body = json.loads(resp.get_body())
        assert body["value"] is None

    def test_cors_header(self):
        resp = json_response({})
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"


class TestErrorResponse:
    def test_basic_error(self):
        resp = error_response("something went wrong")
        assert resp.status_code == 500
        body = json.loads(resp.get_body())
        assert body == {"error": "something went wrong"}

    def test_custom_status(self):
        resp = error_response("not found", 404)
        assert resp.status_code == 404

    def test_unicode(self):
        resp = error_response("Projeto não encontrado")
        body = json.loads(resp.get_body())
        assert "não" in body["error"]


class TestOptionsResponse:
    def test_returns_200(self):
        resp = options_response()
        assert resp.status_code == 200
        assert "Access-Control-Allow-Origin" in resp.headers


class TestHandleErrors:
    def test_passes_through_on_success(self):
        @handle_errors
        def endpoint(req):
            return json_response({"ok": True})

        resp = endpoint(None)
        assert resp.status_code == 200

    def test_catches_not_found_error(self):
        @handle_errors
        def endpoint(req):
            raise NotFoundError("Project", "test-123")

        resp = endpoint(None)
        assert resp.status_code == 404
        body = json.loads(resp.get_body())
        assert "not found" in body["error"]

    def test_catches_validation_error(self):
        @handle_errors
        def endpoint(req):
            raise ValidationError("projectId is required")

        resp = endpoint(None)
        assert resp.status_code == 400

    def test_catches_conflict_error(self):
        @handle_errors
        def endpoint(req):
            raise ConflictError("Cannot cancel completed job")

        resp = endpoint(None)
        assert resp.status_code == 409

    def test_catches_external_service_error(self):
        @handle_errors
        def endpoint(req):
            raise ExternalServiceError("Grok API", "timeout")

        resp = endpoint(None)
        assert resp.status_code == 502

    def test_catches_value_error_as_400(self):
        @handle_errors
        def endpoint(req):
            raise ValueError("bad input")

        resp = endpoint(None)
        assert resp.status_code == 400

    def test_catches_generic_exception_as_500(self):
        @handle_errors
        def endpoint(req):
            raise RuntimeError("unexpected")

        resp = endpoint(None)
        assert resp.status_code == 500

    def test_named_decorator(self):
        @handle_errors("MyEndpoint")
        def endpoint(req):
            raise NotFoundError("Item", "xyz")

        resp = endpoint(None)
        assert resp.status_code == 404
