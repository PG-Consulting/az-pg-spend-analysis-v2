"""Tests for src/api_helpers.py — json_response, error_response, handle_errors."""

import json
import sys
import types

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


class _MockHttpRequest:
    """Minimal mock of azure.functions.HttpRequest for CORS tests."""

    def __init__(self, origin=None):
        self.headers = {"Origin": origin} if origin else {}


_mock_func.HttpResponse = _MockHttpResponse
_mock_azure.functions = _mock_func
sys.modules.setdefault("azure", _mock_azure)
sys.modules.setdefault("azure.functions", _mock_func)

from src.api_helpers import (
    json_response,
    error_response,
    options_response,
    handle_errors,
    _resolve_origin,
    _cors_headers,
    ALLOWED_ORIGINS,
)
from src.exceptions import (
    NotFoundError,
    ValidationError,
    ConflictError,
    ExternalServiceError,
    AuthenticationError,
    ForbiddenError,
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

    def test_cors_header_default(self):
        resp = json_response({})
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_cors_header_with_request(self):
        req = _MockHttpRequest(origin="http://localhost:3000")
        resp = json_response({}, request=req)
        assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"

    def test_credentials_header(self):
        resp = json_response({})
        assert resp.headers.get("Access-Control-Allow-Credentials") == "true"


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

    def test_cors_with_request(self):
        req = _MockHttpRequest(origin="http://localhost:3000")
        resp = error_response("err", 500, request=req)
        assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


class TestOptionsResponse:
    def test_returns_200(self):
        resp = options_response()
        assert resp.status_code == 200
        assert "Access-Control-Allow-Origin" in resp.headers

    def test_old_style_with_methods(self):
        resp = options_response("GET, OPTIONS")
        assert resp.headers["Access-Control-Allow-Methods"] == "GET, OPTIONS"

    def test_new_style_with_request(self):
        req = _MockHttpRequest(origin="http://localhost:3000")
        resp = options_response(req, "POST, OPTIONS")
        assert resp.headers["Access-Control-Allow-Methods"] == "POST, OPTIONS"
        assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"

    def test_authorization_in_allowed_headers(self):
        resp = options_response()
        assert "Authorization" in resp.headers["Access-Control-Allow-Headers"]

    def test_none_first_arg_backwards_compat(self):
        resp = options_response(None, "DELETE, OPTIONS")
        # None is treated as old-style, so methods arg is ignored, uses None as methods
        assert resp.status_code == 200


class TestCorsHelpers:
    def test_resolve_origin_with_allowed(self):
        req = _MockHttpRequest(origin="http://localhost:3000")
        origin = _resolve_origin(req)
        assert origin == "http://localhost:3000"

    def test_resolve_origin_unknown_returns_first(self):
        req = _MockHttpRequest(origin="http://evil.com")
        origin = _resolve_origin(req)
        assert origin == ALLOWED_ORIGINS[0]

    def test_resolve_origin_no_request(self):
        origin = _resolve_origin(None)
        assert origin == ALLOWED_ORIGINS[0]

    def test_cors_headers_include_credentials(self):
        headers = _cors_headers()
        assert headers["Access-Control-Allow-Credentials"] == "true"


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

    def test_catches_filelock_timeout_as_503(self):
        """filelock.Timeout should return 503 with Retry-After header."""
        import filelock

        @handle_errors("TestEndpoint")
        def endpoint(req):
            raise filelock.Timeout("status.json.lock")

        resp = endpoint(None)
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After") == "2"
        body = json.loads(resp.get_body())
        assert "ocupado" in body["error"].lower()

    def test_catches_authentication_error(self):
        @handle_errors
        def endpoint(req):
            raise AuthenticationError()

        resp = endpoint(None)
        assert resp.status_code == 401

    def test_catches_forbidden_error(self):
        @handle_errors
        def endpoint(req):
            raise ForbiddenError()

        resp = endpoint(None)
        assert resp.status_code == 403

    def test_handle_errors_filelock_timeout_uses_dynamic_cors(self):
        """filelock.Timeout branch uses _cors_headers(req) instead of hardcoded '*'."""
        import filelock

        @handle_errors("TestEndpoint")
        def endpoint(req):
            raise filelock.Timeout("status.json.lock")

        req = _MockHttpRequest(origin="http://localhost:3000")
        resp = endpoint(req)
        assert resp.status_code == 503
        assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
        assert resp.headers["Access-Control-Allow-Credentials"] == "true"

    def test_handle_errors_domain_error_uses_dynamic_cors(self):
        @handle_errors("TestEndpoint")
        def endpoint(req):
            raise ValidationError("bad")

        req = _MockHttpRequest(origin="http://localhost:3000")
        resp = endpoint(req)
        assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"

    def test_handle_errors_generic_error_uses_dynamic_cors(self):
        @handle_errors("TestEndpoint")
        def endpoint(req):
            raise RuntimeError("boom")

        req = _MockHttpRequest(origin="http://localhost:3000")
        resp = endpoint(req)
        assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


class TestSecurityHeaders:
    def test_cors_headers_include_security_headers(self):
        from src.api_helpers import _cors_headers

        headers = _cors_headers()
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_json_response_includes_security_headers(self):
        from src.api_helpers import json_response

        resp = json_response({"ok": True})
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
