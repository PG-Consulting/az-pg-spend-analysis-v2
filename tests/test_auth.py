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

        # MUST raise — token without groups claim is not trusted
        with pytest.raises(ForbiddenError):
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
        with pytest.raises(AuthenticationError, match="Authentication required"):
            endpoint(req)

    def test_invalid_token_returns_generic_message(self, monkeypatch):
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        monkeypatch.setenv("AZURE_AD_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_AD_CLIENT_ID", "test-client")
        from src.auth import _extract_and_validate

        req = _MockHttpRequest(headers={"Authorization": "Bearer invalid.token.here"})
        with pytest.raises(AuthenticationError, match="Authentication required"):
            _extract_and_validate(req)


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


@pytest.mark.real_auth
class TestValidateJwtTokenIssuers:
    """Tests that exercise _validate_jwt_token directly with real RSA keys and JWTs."""

    @staticmethod
    def _make_rsa_pair():
        """Generate a real RSA key pair and return (private_key, jwk_dict, kid)."""
        import base64
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        public_key = private_key.public_key()
        pub_numbers = public_key.public_numbers()

        def _int_to_base64(n: int) -> str:
            byte_length = (n.bit_length() + 7) // 8
            return (
                base64.urlsafe_b64encode(n.to_bytes(byte_length, byteorder="big"))
                .rstrip(b"=")
                .decode("ascii")
            )

        kid = "test-key-id"
        jwk_dict = {
            "kid": kid,
            "kty": "RSA",
            "n": _int_to_base64(pub_numbers.n),
            "e": _int_to_base64(pub_numbers.e),
        }
        return private_key, jwk_dict, kid

    @staticmethod
    def _make_token(
        private_key, kid: str, issuer: str, audience: str = "api://test-client"
    ) -> str:
        """Encode a real JWT signed with the given private key."""
        import time
        import jwt as pyjwt

        now = int(time.time())
        payload = {
            "iss": issuer,
            "aud": audience,
            "preferred_username": "user@test.com",
            "name": "Test User",
            "iat": now,
            "nbf": now,
            "exp": now + 3600,
        }
        token = pyjwt.encode(
            payload,
            private_key,
            algorithm="RS256",
            headers={"kid": kid},
        )
        return token

    @patch("src.auth._get_jwks_keys")
    @patch("jwt.get_unverified_header")
    def test_v2_issuer_accepted(self, mock_header, mock_jwks, monkeypatch):
        """JWT with v2.0 issuer must be accepted by _validate_jwt_token."""
        monkeypatch.setenv("AZURE_AD_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_AD_CLIENT_ID", "test-client")

        from src.auth import _validate_jwt_token

        private_key, jwk_dict, kid = self._make_rsa_pair()
        issuer = "https://login.microsoftonline.com/test-tenant/v2.0"
        token = self._make_token(private_key, kid, issuer)

        mock_header.return_value = {"kid": kid, "alg": "RS256"}
        mock_jwks.return_value = [jwk_dict]

        claims = _validate_jwt_token(token)
        assert claims["preferred_username"] == "user@test.com"
        assert claims["iss"] == issuer

    @patch("src.auth._get_jwks_keys")
    @patch("jwt.get_unverified_header")
    def test_v1_issuer_accepted(self, mock_header, mock_jwks, monkeypatch):
        """JWT with v1.0 issuer (sts.windows.net) must be accepted."""
        monkeypatch.setenv("AZURE_AD_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_AD_CLIENT_ID", "test-client")

        from src.auth import _validate_jwt_token

        private_key, jwk_dict, kid = self._make_rsa_pair()
        issuer = "https://sts.windows.net/test-tenant/"
        token = self._make_token(private_key, kid, issuer)

        mock_header.return_value = {"kid": kid, "alg": "RS256"}
        mock_jwks.return_value = [jwk_dict]

        claims = _validate_jwt_token(token)
        assert claims["preferred_username"] == "user@test.com"
        assert claims["iss"] == issuer

    @patch("src.auth._get_jwks_keys")
    @patch("jwt.get_unverified_header")
    def test_unknown_issuer_rejected(self, mock_header, mock_jwks, monkeypatch):
        """JWT with an unknown issuer must raise AuthenticationError."""
        monkeypatch.setenv("AZURE_AD_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_AD_CLIENT_ID", "test-client")

        from src.auth import _validate_jwt_token

        private_key, jwk_dict, kid = self._make_rsa_pair()
        issuer = "https://evil.example.com/"
        token = self._make_token(private_key, kid, issuer)

        mock_header.return_value = {"kid": kid, "alg": "RS256"}
        mock_jwks.return_value = [jwk_dict]

        with pytest.raises(AuthenticationError, match="Invalid token issuer"):
            _validate_jwt_token(token)
