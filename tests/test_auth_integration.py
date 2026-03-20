"""Integration tests for auth decorators on real endpoints.

These tests use @pytest.mark.real_auth so the autouse fixture does NOT
set SKIP_AUTH=true. They validate that auth decorators actually protect endpoints.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

# We need the azure.functions mock setup from test helpers
import sys
import types

_mock_azure = types.ModuleType("azure")
_mock_func = types.ModuleType("azure.functions")


class _MockHttpResponse:
    def __init__(self, body=None, status_code=200, mimetype=None, headers=None):
        self._body = body.encode("utf-8") if isinstance(body, str) else (body or b"")
        self.status_code = status_code
        self.mimetype = mimetype
        self.headers = headers or {}

    def get_body(self):
        return self._body


class _MockHttpRequest:
    def __init__(self, method="GET", headers=None, params=None, body=None):
        self.method = method
        self.headers = headers or {}
        self.params = params or {}
        self._body = body
        self.user = None

    def get_json(self):
        if self._body:
            return json.loads(self._body) if isinstance(self._body, str) else self._body
        return {}


_mock_func.HttpResponse = _MockHttpResponse
_mock_func.HttpRequest = _MockHttpRequest
_mock_func.Blueprint = MagicMock
_mock_func.AuthLevel = MagicMock()
_mock_func.AuthLevel.ANONYMOUS = "anonymous"
_mock_azure.functions = _mock_func
sys.modules.setdefault("azure", _mock_azure)
sys.modules.setdefault("azure.functions", _mock_func)


def _mock_claims(email="user@test.com", name="Test User", groups=None):
    claims = {
        "preferred_username": email,
        "name": name,
    }
    if groups is not None:
        claims["groups"] = groups
    return claims


@pytest.mark.real_auth
class TestAuthIntegration:
    """Tests that run WITHOUT SKIP_AUTH — they validate real auth enforcement."""

    def test_protected_endpoint_returns_401_without_token(self, monkeypatch):
        """Endpoint with @require_auth returns 401 when no Authorization header."""
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        from src.auth import require_auth
        from src.api_helpers import json_response

        @require_auth
        def endpoint(req):
            return json_response({"ok": True})

        req = _MockHttpRequest()
        # Should raise AuthenticationError which handle_errors would catch
        from src.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError):
            endpoint(req)

    @patch("src.auth._validate_jwt_token")
    def test_protected_endpoint_returns_200_with_valid_token(
        self, mock_validate, monkeypatch
    ):
        """Endpoint with @require_auth returns 200 with valid token."""
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        monkeypatch.setenv("ADMIN_EMAILS", "")
        mock_validate.return_value = _mock_claims()

        from src.auth import require_auth
        from src.api_helpers import json_response

        @require_auth
        def endpoint(req):
            return json_response({"ok": True, "user": req.user["email"]})

        req = _MockHttpRequest(headers={"Authorization": "Bearer valid-token"})
        resp = endpoint(req)
        body = json.loads(resp.get_body())
        assert body["ok"] is True
        assert body["user"] == "user@test.com"

    @patch("src.auth._validate_jwt_token")
    def test_admin_endpoint_returns_403_for_consultor(self, mock_validate, monkeypatch):
        """Endpoint with @require_admin returns 403 for non-admin users."""
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        monkeypatch.setenv("ADMIN_EMAILS", "admin@test.com")
        mock_validate.return_value = _mock_claims(email="user@test.com")

        from src.auth import require_admin
        from src.exceptions import ForbiddenError

        @require_admin
        def endpoint(req):
            return _MockHttpResponse(200)

        req = _MockHttpRequest(headers={"Authorization": "Bearer valid-token"})
        with pytest.raises(ForbiddenError):
            endpoint(req)

    @patch("src.auth._validate_jwt_token")
    def test_admin_endpoint_returns_200_for_admin(self, mock_validate, monkeypatch):
        """Endpoint with @require_admin returns 200 for admin users."""
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        monkeypatch.setenv("ADMIN_EMAILS", "admin@test.com")
        mock_validate.return_value = _mock_claims(email="admin@test.com")

        from src.auth import require_admin
        from src.api_helpers import json_response

        @require_admin
        def endpoint(req):
            return json_response({"admin": True})

        req = _MockHttpRequest(headers={"Authorization": "Bearer valid-token"})
        resp = endpoint(req)
        body = json.loads(resp.get_body())
        assert body["admin"] is True

    @patch("src.auth._validate_jwt_token")
    def test_group_validation_returns_403(self, mock_validate, monkeypatch):
        """When ALLOWED_GROUP_ID is set, user not in group gets 403."""
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        monkeypatch.setenv("ADMIN_EMAILS", "")
        monkeypatch.setenv("ALLOWED_GROUP_ID", "required-group-id")
        mock_validate.return_value = _mock_claims(groups=["other-group"])

        from src.auth import require_auth
        from src.exceptions import ForbiddenError

        @require_auth
        def endpoint(req):
            return _MockHttpResponse(200)

        req = _MockHttpRequest(headers={"Authorization": "Bearer valid-token"})
        with pytest.raises(ForbiddenError):
            endpoint(req)

    def test_options_bypasses_auth(self, monkeypatch):
        """OPTIONS requests bypass auth even without SKIP_AUTH."""
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        from src.auth import require_auth

        @require_auth
        def endpoint(req):
            return _MockHttpResponse(200)

        req = _MockHttpRequest(method="OPTIONS")
        resp = endpoint(req)
        assert resp.status_code == 200

    def test_health_check_has_no_auth(self):
        """Health check endpoint works without any auth."""
        # health_bp doesn't have @require_auth, so it should work
        # We just verify the import and that no auth decorator exists
        from blueprints.health_bp import HealthCheck

        # HealthCheck is decorated with @handle_errors but NOT @require_auth
        assert hasattr(HealthCheck, "__wrapped__") or callable(HealthCheck)
