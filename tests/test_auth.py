"""Tests for src/auth.py — JWT authentication module."""

import pytest
from unittest.mock import patch

from src.exceptions import AuthenticationError, ForbiddenError


class _MockHttpRequest:
    """Minimal mock of azure.functions.HttpRequest."""

    def __init__(self, headers=None, method="GET"):
        self.headers = headers or {}
        self.method = method
        self.user = None


class _MockHttpResponse:
    """Minimal mock for response."""

    def __init__(self, status_code=200):
        self.status_code = status_code


# Patch _validate_jwt_token to avoid real JWKS calls
def _mock_claims(email="user@test.com", name="Test User", groups=None):
    claims = {
        "preferred_username": email,
        "name": name,
        "exp": 9999999999,
        "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
        "aud": "test-client",
    }
    if groups is not None:
        claims["groups"] = groups
    return claims


class TestResolveRole:
    def test_admin_email(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAILS", "admin@test.com, boss@test.com")
        from src.auth import _resolve_role

        assert _resolve_role("admin@test.com") == "admin"

    def test_admin_email_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAILS", "Admin@Test.com")
        from src.auth import _resolve_role

        assert _resolve_role("admin@test.com") == "admin"

    def test_non_admin_email(self, monkeypatch):
        monkeypatch.setenv("ADMIN_EMAILS", "admin@test.com")
        from src.auth import _resolve_role

        assert _resolve_role("user@test.com") == "consultor"

    def test_no_admin_emails_configured(self, monkeypatch):
        monkeypatch.delenv("ADMIN_EMAILS", raising=False)
        from src.auth import _resolve_role

        assert _resolve_role("anyone@test.com") == "consultor"


class TestValidateGroupClaim:
    def test_no_group_required(self, monkeypatch):
        monkeypatch.delenv("ALLOWED_GROUP_ID", raising=False)
        from src.auth import _validate_group_claim

        _validate_group_claim({})  # Should not raise

    def test_group_present_and_matching(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_GROUP_ID", "group-123")
        from src.auth import _validate_group_claim

        _validate_group_claim({"groups": ["group-123", "other"]})

    def test_group_present_but_not_matching(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_GROUP_ID", "group-123")
        from src.auth import _validate_group_claim

        with pytest.raises(ForbiddenError):
            _validate_group_claim({"groups": ["other-group"]})

    def test_group_required_but_no_groups_claim(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_GROUP_ID", "group-123")
        from src.auth import _validate_group_claim

        # Should NOT raise — IdP not configured to emit groups
        _validate_group_claim({"preferred_username": "user@test.com"})


class TestIsSkipAuthAllowed:
    def test_skip_auth_true_local(self, monkeypatch):
        monkeypatch.setenv("SKIP_AUTH", "true")
        monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
        from src.auth import _is_skip_auth_allowed

        assert _is_skip_auth_allowed() is True

    def test_skip_auth_true_azure(self, monkeypatch):
        monkeypatch.setenv("SKIP_AUTH", "true")
        monkeypatch.setenv("WEBSITE_SITE_NAME", "my-func-app")
        from src.auth import _is_skip_auth_allowed

        assert _is_skip_auth_allowed() is False

    def test_skip_auth_false(self, monkeypatch):
        monkeypatch.setenv("SKIP_AUTH", "false")
        monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
        from src.auth import _is_skip_auth_allowed

        assert _is_skip_auth_allowed() is False


class TestRequireAuth:
    def test_bypasses_options(self):
        from src.auth import require_auth

        @require_auth
        def endpoint(req):
            return _MockHttpResponse(200)

        req = _MockHttpRequest(method="OPTIONS")
        resp = endpoint(req)
        assert resp.status_code == 200

    def test_skip_auth_injects_dev_user(self, monkeypatch):
        monkeypatch.setenv("SKIP_AUTH", "true")
        monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
        from src.auth import require_auth

        @require_auth
        def endpoint(req):
            return req.user

        req = _MockHttpRequest()
        user = endpoint(req)
        assert user["email"] == "dev@local"
        assert user["role"] == "admin"

    @patch("src.auth._validate_jwt_token")
    def test_valid_token(self, mock_validate, monkeypatch):
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        monkeypatch.setenv("ADMIN_EMAILS", "")
        mock_validate.return_value = _mock_claims()
        from src.auth import require_auth

        @require_auth
        def endpoint(req):
            return req.user

        req = _MockHttpRequest(headers={"Authorization": "Bearer valid-token"})
        user = endpoint(req)
        assert user["email"] == "user@test.com"
        assert user["role"] == "consultor"

    def test_missing_auth_header(self, monkeypatch):
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        from src.auth import require_auth

        @require_auth
        def endpoint(req):
            return _MockHttpResponse(200)

        req = _MockHttpRequest()
        with pytest.raises(AuthenticationError):
            endpoint(req)


class TestRequireAdmin:
    @patch("src.auth._validate_jwt_token")
    def test_admin_allowed(self, mock_validate, monkeypatch):
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        monkeypatch.setenv("ADMIN_EMAILS", "admin@test.com")
        mock_validate.return_value = _mock_claims(email="admin@test.com")
        from src.auth import require_admin

        @require_admin
        def endpoint(req):
            return req.user

        req = _MockHttpRequest(headers={"Authorization": "Bearer valid-token"})
        user = endpoint(req)
        assert user["role"] == "admin"

    @patch("src.auth._validate_jwt_token")
    def test_non_admin_rejected(self, mock_validate, monkeypatch):
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        monkeypatch.setenv("ADMIN_EMAILS", "admin@test.com")
        mock_validate.return_value = _mock_claims(email="user@test.com")
        from src.auth import require_admin

        @require_admin
        def endpoint(req):
            return _MockHttpResponse(200)

        req = _MockHttpRequest(headers={"Authorization": "Bearer valid-token"})
        with pytest.raises(ForbiddenError):
            endpoint(req)

    def test_bypasses_options(self):
        from src.auth import require_admin

        @require_admin
        def endpoint(req):
            return _MockHttpResponse(200)

        req = _MockHttpRequest(method="OPTIONS")
        resp = endpoint(req)
        assert resp.status_code == 200
