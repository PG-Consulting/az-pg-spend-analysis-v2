"""JWT authentication module for Azure Entra ID (Azure AD).

Validates RS256 JWTs, resolves user roles, and provides decorators
for protecting Azure Functions endpoints.
"""

import os
import time
import logging
import functools

import jwt
import requests

from src.exceptions import AuthenticationError, ForbiddenError

logger = logging.getLogger(__name__)

# --- JWKS cache ---
_jwks_cache = {"keys": None, "fetched_at": 0}
_JWKS_TTL = 86400  # 24 hours


def _get_jwks_keys(tenant_id: str) -> list:
    """Fetch and cache JWKS public keys from Azure AD.

    Refreshes after TTL expiry or when a kid is not found (key rotation).
    """
    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < _JWKS_TTL:
        return _jwks_cache["keys"]

    jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    try:
        resp = requests.get(jwks_url, timeout=10)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
        _jwks_cache["keys"] = keys
        _jwks_cache["fetched_at"] = now
        logger.info(f"JWKS refreshed: {len(keys)} keys loaded")
        return keys
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        if _jwks_cache["keys"]:
            return _jwks_cache["keys"]
        raise AuthenticationError("Unable to validate token — JWKS unavailable")


def _validate_jwt_token(token: str) -> dict:
    """Validate a JWT token against Azure AD JWKS keys.

    Returns the decoded claims dict.
    Raises AuthenticationError on any validation failure.
    """
    tenant_id = os.environ.get("AZURE_AD_TENANT_ID", "")
    client_id = os.environ.get("AZURE_AD_CLIENT_ID", "")

    if not tenant_id or not client_id:
        raise AuthenticationError(
            "Auth not configured (missing AZURE_AD_TENANT_ID or AZURE_AD_CLIENT_ID)"
        )

    # Decode header to find kid
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.DecodeError:
        raise AuthenticationError("Invalid token format")

    kid = unverified_header.get("kid")
    if not kid:
        raise AuthenticationError("Token missing kid header")

    # Find matching key
    keys = _get_jwks_keys(tenant_id)
    rsa_key = None
    for key in keys:
        if key.get("kid") == kid:
            rsa_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
            break

    if rsa_key is None:
        # Try refreshing keys (key rotation)
        _jwks_cache["fetched_at"] = 0
        keys = _get_jwks_keys(tenant_id)
        for key in keys:
            if key.get("kid") == kid:
                rsa_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                break

    if rsa_key is None:
        raise AuthenticationError("Token signed with unknown key")

    issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    # Access tokens for custom API scopes (api://{clientId}/...) have
    # audience = "api://{clientId}", not the bare clientId.
    audience = f"api://{client_id}"

    try:
        claims = jwt.decode(
            token,
            key=rsa_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
        )
        return claims
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token expired")
    except jwt.InvalidAudienceError:
        raise AuthenticationError("Invalid token audience")
    except jwt.InvalidIssuerError:
        raise AuthenticationError("Invalid token issuer")
    except jwt.PyJWTError as e:
        raise AuthenticationError(f"Token validation failed: {e}")


def _resolve_role(email: str) -> str:
    """Resolve user role from ADMIN_EMAILS env var.

    Returns 'admin' if email is in the list (case-insensitive), else 'consultor'.
    """
    admin_emails_raw = os.environ.get("ADMIN_EMAILS", "")
    if not admin_emails_raw:
        return "consultor"
    admin_emails = {e.strip().lower() for e in admin_emails_raw.split(",") if e.strip()}
    return "admin" if email.lower() in admin_emails else "consultor"


def _validate_group_claim(claims: dict) -> None:
    """Validate that the user belongs to the required group.

    Only enforced if ALLOWED_GROUP_ID is set. If the claim 'groups' is absent,
    raises ForbiddenError — token without group membership is not trusted.
    """
    allowed_group = os.environ.get("ALLOWED_GROUP_ID", "").strip()
    if not allowed_group:
        return

    groups = claims.get("groups", [])
    if not groups:
        logger.warning(
            "ALLOWED_GROUP_ID set but token has no 'groups' claim — blocking access"
        )
        raise ForbiddenError("Token missing required group membership claim")

    if allowed_group not in groups:
        raise ForbiddenError("User is not a member of the required security group")


def _is_skip_auth_allowed() -> bool:
    """Check if SKIP_AUTH=true is allowed (only in local dev, not on Azure)."""
    skip = os.environ.get("SKIP_AUTH", "").lower() == "true"
    on_azure = bool(os.environ.get("WEBSITE_SITE_NAME"))
    return skip and not on_azure


def _extract_and_validate(req) -> dict:
    """Extract and validate JWT from request. Returns user info dict."""
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthenticationError()  # default: "Authentication required"

    token = auth_header[7:]
    try:
        claims = _validate_jwt_token(token)
    except AuthenticationError as e:
        # Log specific reason + client IP for debugging in production
        logger.warning(
            "JWT validation failed for %s: %s",
            req.headers.get("X-Forwarded-For", "unknown-ip"),
            e,
        )
        raise AuthenticationError()  # default: "Authentication required"

    # Validate group membership
    _validate_group_claim(claims)

    email = claims.get("preferred_username", claims.get("email", claims.get("upn", "")))
    name = claims.get("name", email)
    role = _resolve_role(email)

    return {
        "email": email,
        "name": name,
        "role": role,
        "claims": claims,
    }


def require_auth(fn):
    """Decorator: requires valid JWT. Bypasses OPTIONS preflight.

    Injects req.user = {email, name, role, claims} on success.
    If SKIP_AUTH=true (local dev only), injects a mock user.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        req = args[0] if args else kwargs.get("req")

        # Bypass OPTIONS preflight
        if req and hasattr(req, "method") and req.method == "OPTIONS":
            return fn(*args, **kwargs)

        # Dev bypass
        if _is_skip_auth_allowed():
            if req:
                req.user = {
                    "email": "dev@local",
                    "name": "Dev User",
                    "role": "admin",
                    "claims": {},
                }
            return fn(*args, **kwargs)

        if not req:
            raise AuthenticationError("No request object")

        user = _extract_and_validate(req)
        req.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    """Decorator: requires valid JWT + admin role. Autocontido (não empilhar com require_auth)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        req = args[0] if args else kwargs.get("req")

        # Bypass OPTIONS preflight
        if req and hasattr(req, "method") and req.method == "OPTIONS":
            return fn(*args, **kwargs)

        # Dev bypass
        if _is_skip_auth_allowed():
            if req:
                req.user = {
                    "email": "dev@local",
                    "name": "Dev User",
                    "role": "admin",
                    "claims": {},
                }
            return fn(*args, **kwargs)

        if not req:
            raise AuthenticationError("No request object")

        user = _extract_and_validate(req)
        if user["role"] != "admin":
            raise ForbiddenError("Admin access required")
        req.user = user
        return fn(*args, **kwargs)

    return wrapper
