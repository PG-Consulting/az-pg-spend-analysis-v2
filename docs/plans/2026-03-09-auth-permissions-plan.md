# Autenticação Entra ID + Permissões — Plano de Implementação

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Adicionar autenticação via Microsoft Entra ID (MSAL.js) e controle de acesso baseado em 2 roles (Consultor/Admin) à plataforma Spend Analysis v3.

**Architecture:** Frontend usa `@azure/msal-react` para login, obtém JWT do Entra ID, envia como `Authorization: Bearer <token>` em todas as requests. Backend valida JWT via `PyJWT`, extrai email e resolve role (admin se email em `ADMIN_EMAILS`). Decorators `@require_auth` e `@require_admin` protegem endpoints.

**Tech Stack:** `@azure/msal-browser`, `@azure/msal-react`, `PyJWT`, `cryptography`

**Design doc:** `docs/plans/2026-03-09-auth-permissions-design.md`

---

## Pré-requisito Manual: App Registration no Azure

Antes de começar a implementação, registrar o app no portal Azure:
1. Azure AD → App registrations → New registration
2. Nome: "Spend Analysis v3"
3. Tipo: SPA
4. Redirect URIs: `http://localhost:3000` + URL de produção
5. Permissões: `User.Read` (Microsoft Graph)
6. Anotar: `AZURE_AD_TENANT_ID` e `AZURE_AD_CLIENT_ID`

---

## Task 1: Exceções de Auth (`src/exceptions.py`)

**Files:**
- Modify: `src/exceptions.py`
- Test: `tests/test_exceptions.py`

**Step 1: Escrever os testes**

```python
# tests/test_exceptions.py — adicionar ao final do arquivo (ou criar se não existir)

from src.exceptions import AuthenticationError, ForbiddenError, SpendAnalysisError

def test_authentication_error_defaults():
    err = AuthenticationError()
    assert str(err) == "Autenticação necessária"
    assert err.status_code == 401
    assert isinstance(err, SpendAnalysisError)

def test_authentication_error_custom_message():
    err = AuthenticationError("Token expirado")
    assert str(err) == "Token expirado"
    assert err.status_code == 401

def test_forbidden_error_defaults():
    err = ForbiddenError()
    assert str(err) == "Acesso restrito a administradores"
    assert err.status_code == 403
    assert isinstance(err, SpendAnalysisError)

def test_forbidden_error_custom_message():
    err = ForbiddenError("Sem permissão para esta operação")
    assert str(err) == "Sem permissão para esta operação"
    assert err.status_code == 403
```

**Step 2: Rodar testes — devem falhar**

Run: `python3 -m pytest tests/test_exceptions.py -v -k "auth or forbidden"`
Expected: FAIL — ImportError (classes não existem)

**Step 3: Implementar as exceções**

Adicionar ao final de `src/exceptions.py`:

```python
class AuthenticationError(SpendAnalysisError):
    """Authentication required or token invalid (401)."""

    def __init__(self, message: str = "Autenticação necessária"):
        super().__init__(message, status_code=401)


class ForbiddenError(SpendAnalysisError):
    """Insufficient permissions (403)."""

    def __init__(self, message: str = "Acesso restrito a administradores"):
        super().__init__(message, status_code=403)
```

**Step 4: Rodar testes — devem passar**

Run: `python3 -m pytest tests/test_exceptions.py -v -k "auth or forbidden"`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/exceptions.py tests/test_exceptions.py
git commit -m "Adicionando AuthenticationError e ForbiddenError em exceptions.py"
```

---

## Task 2: CORS — Atualizar `api_helpers.py`

**Files:**
- Modify: `src/api_helpers.py`
- Test: `tests/test_api_helpers.py`

**Step 1: Escrever os testes**

```python
# tests/test_api_helpers.py — adicionar testes para CORS

import azure.functions as func
from unittest.mock import MagicMock
from src.api_helpers import json_response, error_response, options_response, ALLOWED_ORIGINS

def _make_request(origin: str = "http://localhost:3000") -> func.HttpRequest:
    return func.HttpRequest(
        method="OPTIONS",
        url="http://localhost:7071/api/test",
        headers={"Origin": origin},
        body=b"",
    )

def test_options_response_includes_authorization_header():
    req = _make_request()
    resp = options_response(req)
    assert "Authorization" in resp.headers["Access-Control-Allow-Headers"]
    assert "Content-Type" in resp.headers["Access-Control-Allow-Headers"]

def test_options_response_includes_credentials():
    req = _make_request()
    resp = options_response(req)
    assert resp.headers["Access-Control-Allow-Credentials"] == "true"

def test_options_response_includes_max_age():
    req = _make_request()
    resp = options_response(req)
    assert resp.headers["Access-Control-Max-Age"] == "3600"

def test_options_response_echoes_allowed_origin():
    req = _make_request("http://localhost:3000")
    resp = options_response(req)
    assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"

def test_options_response_rejects_unknown_origin():
    req = _make_request("http://evil.com")
    resp = options_response(req)
    # Deve retornar a primeira origin permitida ou string vazia, não a origin maliciosa
    assert resp.headers["Access-Control-Allow-Origin"] != "http://evil.com"

def test_json_response_cors_origin():
    req = _make_request("http://localhost:3000")
    resp = json_response({"ok": True}, request=req)
    assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert resp.headers["Access-Control-Allow-Credentials"] == "true"

def test_error_response_cors_origin():
    req = _make_request("http://localhost:3000")
    resp = error_response("fail", 400, request=req)
    assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert resp.headers["Access-Control-Allow-Credentials"] == "true"

def test_json_response_without_request_uses_first_origin():
    resp = json_response({"ok": True})
    assert resp.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGINS[0]

def test_error_response_without_request_uses_first_origin():
    resp = error_response("fail", 400)
    assert resp.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGINS[0]
```

**Step 2: Rodar testes — devem falhar**

Run: `python3 -m pytest tests/test_api_helpers.py -v -k "cors or origin or credential"`
Expected: FAIL

**Step 3: Implementar mudanças no `api_helpers.py`**

Reescrever `api_helpers.py` com as seguintes mudanças:
1. Adicionar constante `ALLOWED_ORIGINS` lida de env var `ALLOWED_ORIGINS` (default `["http://localhost:3000"]`)
2. Helper `_resolve_origin(req)` — ecoa `Origin` se está na lista, senão retorna primeiro da lista
3. `options_response(req, methods)` — novo parâmetro `req` obrigatório
4. `json_response(data, status_code, headers, request)` — parâmetro `request` opcional
5. `error_response(message, status_code, request)` — parâmetro `request` opcional
6. Todas as respostas incluem `Access-Control-Allow-Credentials: true`

```python
"""Standardized API response helpers and error handling decorator."""
import json
import logging
import os
import functools

import azure.functions as func

from src.utils import safe_json_dumps
from src.exceptions import SpendAnalysisError

logger = logging.getLogger(__name__)

ALLOWED_ORIGINS: list[str] = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]


def _resolve_origin(request: func.HttpRequest | None = None) -> str:
    """Return the request Origin if it's in ALLOWED_ORIGINS, else first allowed."""
    if request:
        origin = request.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            return origin
    return ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else ""


def _cors_headers(request: func.HttpRequest | None = None) -> dict:
    return {
        "Access-Control-Allow-Origin": _resolve_origin(request),
        "Access-Control-Allow-Credentials": "true",
    }


def json_response(
    data, status_code: int = 200, headers: dict = None, request: func.HttpRequest = None
) -> func.HttpResponse:
    """Create a JSON HttpResponse using safe_json_dumps."""
    resp_headers = _cors_headers(request)
    if headers:
        resp_headers.update(headers)
    return func.HttpResponse(
        body=safe_json_dumps(data),
        status_code=status_code,
        mimetype="application/json",
        headers=resp_headers,
    )


def error_response(
    message: str, status_code: int = 500, request: func.HttpRequest = None
) -> func.HttpResponse:
    """Create a standardized error response: {"error": "message"}."""
    return func.HttpResponse(
        body=json.dumps({"error": message}, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
        headers=_cors_headers(request),
    )


def options_response(
    req: func.HttpRequest, methods: str = "GET, POST, OPTIONS"
) -> func.HttpResponse:
    """Create a CORS preflight response."""
    return func.HttpResponse(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": _resolve_origin(req),
            "Access-Control-Allow-Methods": methods,
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "3600",
        },
    )


# handle_errors permanece igual (sem mudanças)
```

**Step 4: Atualizar chamadas existentes em TODOS os blueprints**

Todos os blueprints que chamam `options_response()` (sem `req`) ou `json_response()`/`error_response()` precisam passar `req`.

Para `options_response`: nos blueprints que já usam (classification_bp, models_bp, copilot_bp), mudar `options_response()` para `options_response(req)`.

Para `json_response` e `error_response`: adicionar `request=req` como keyword argument. **Fazer em todas as chamadas é muito invasivo neste momento** — como o parâmetro é optional e o default usa `ALLOWED_ORIGINS[0]`, as chamadas existentes continuam funcionando sem `request=`. Atualizar progressivamente.

**Nota**: `@handle_errors` captura exceções e chama `error_response()`. Como o decorator não tem acesso ao `req`, ele não poderá passar `request=`. Para resolver, o wrapper pode extrair `req` dos args:

```python
def handle_errors(func_or_name=None):
    def decorator(fn):
        endpoint_name = func_or_name if isinstance(func_or_name, str) else fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Extrair req dos args para CORS em error_response
            req = args[0] if args and isinstance(args[0], func.HttpRequest) else None
            try:
                return fn(*args, **kwargs)
            except SpendAnalysisError as e:
                logger.warning(f"{endpoint_name}: {e}")
                return error_response(str(e), e.status_code, request=req)
            except ValueError as e:
                logger.warning(f"{endpoint_name} validation error: {e}")
                return error_response(str(e), 400, request=req)
            except Exception as e:
                logger.error(f"{endpoint_name} error: {e}", exc_info=True)
                return error_response(str(e), 500, request=req)

        return wrapper

    if callable(func_or_name):
        return decorator(func_or_name)
    return decorator
```

**Step 5: Rodar testes — devem passar**

Run: `python3 -m pytest tests/test_api_helpers.py -v`
Expected: PASS

**Step 6: Rodar todos os testes do backend**

Run: `python3 -m pytest tests/ -v`
Expected: 267+ passed (sem regressão — `json_response()` e `error_response()` sem `request=` continuam funcionando)

**Step 7: Commit**

```bash
git add src/api_helpers.py tests/test_api_helpers.py
git commit -m "Ajuste CORS: origin dinâmica, Authorization header, credentials"
```

---

## Task 3: CORS — Atualizar `host.json`

**Files:**
- Modify: `host.json`

**Step 1: Remover CORS do host.json**

Conforme design doc, é mais seguro tratar CORS inteiramente na camada de aplicação. Remover a seção `cors` do `host.json`:

```json
{
  "version": "2.0",
  "functionTimeout": "00:30:00",
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  },
  "extensions": {
    "http": {
      "maxOutstandingRequests": 200,
      "maxConcurrentRequests": 100,
      "routePrefix": "api"
    }
  },
  "logging": {
    "logLevel": {
      "default": "Information",
      "Host.Results": "Error",
      "Function": "Information",
      "Host.Aggregator": "Trace"
    }
  }
}
```

**Step 2: Commit**

```bash
git add host.json
git commit -m "Ajuste: remove CORS do host.json — tratado na camada de aplicação"
```

---

## Task 4: Módulo de Auth — `src/auth.py`

**Files:**
- Create: `src/auth.py`
- Test: `tests/test_auth.py`

**Step 1: Escrever os testes**

```python
# tests/test_auth.py

import json
import time
from unittest.mock import patch, MagicMock
import azure.functions as func
import pytest

from src.exceptions import AuthenticationError, ForbiddenError


def _make_request(method="GET", token=None, origin="http://localhost:3000"):
    headers = {"Origin": origin}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return func.HttpRequest(
        method=method,
        url="http://localhost:7071/api/test",
        headers=headers,
        body=b"",
    )


# ---- SKIP_AUTH tests ----

@patch.dict("os.environ", {"SKIP_AUTH": "true"}, clear=False)
@patch.dict("os.environ", {}, clear=False)  # no WEBSITE_SITE_NAME
def test_skip_auth_in_local_dev():
    """SKIP_AUTH=true sem WEBSITE_SITE_NAME deve bypassar auth."""
    from src.auth import require_auth
    # Remover WEBSITE_SITE_NAME se existir
    import os
    os.environ.pop("WEBSITE_SITE_NAME", None)
    os.environ["SKIP_AUTH"] = "true"

    called = False
    @require_auth
    def handler(req):
        nonlocal called
        called = True
        return func.HttpResponse("ok", status_code=200)

    req = _make_request()  # sem token
    resp = handler(req)
    assert called
    assert resp.status_code == 200


@patch.dict("os.environ", {"SKIP_AUTH": "true", "WEBSITE_SITE_NAME": "my-func-app"})
def test_skip_auth_ignored_in_azure():
    """SKIP_AUTH=true COM WEBSITE_SITE_NAME deve ser ignorado — auth obrigatória."""
    # Re-import para pegar env vars atualizadas
    import importlib
    import src.auth
    importlib.reload(src.auth)
    from src.auth import require_auth

    @require_auth
    def handler(req):
        return func.HttpResponse("ok", status_code=200)

    req = _make_request()  # sem token
    with pytest.raises(AuthenticationError):
        handler(req)


# ---- OPTIONS bypass tests ----

def test_require_auth_bypasses_options():
    from src.auth import require_auth

    @require_auth
    def handler(req):
        return func.HttpResponse("ok", status_code=200)

    req = _make_request(method="OPTIONS")
    resp = handler(req)
    assert resp.status_code == 200


def test_require_admin_bypasses_options():
    from src.auth import require_admin

    @require_admin
    def handler(req):
        return func.HttpResponse("ok", status_code=200)

    req = _make_request(method="OPTIONS")
    resp = handler(req)
    assert resp.status_code == 200


# ---- Missing token tests ----

def test_require_auth_no_token_raises():
    from src.auth import require_auth

    @require_auth
    def handler(req):
        return func.HttpResponse("ok")

    req = _make_request()  # sem token
    with pytest.raises(AuthenticationError):
        handler(req)


def test_require_auth_malformed_token_raises():
    from src.auth import require_auth

    @require_auth
    def handler(req):
        return func.HttpResponse("ok")

    req = _make_request(token="not-a-jwt")
    with pytest.raises(AuthenticationError):
        handler(req)


# ---- Admin email resolution tests ----

@patch.dict("os.environ", {"ADMIN_EMAILS": "admin@pg.com, Admin2@PG.COM "})
def test_resolve_role_admin_case_insensitive():
    from src.auth import _resolve_role
    assert _resolve_role("admin@pg.com") == "admin"
    assert _resolve_role("ADMIN@PG.COM") == "admin"
    assert _resolve_role("admin2@pg.com") == "admin"
    assert _resolve_role("user@pg.com") == "consultor"


@patch.dict("os.environ", {"ADMIN_EMAILS": ""})
def test_resolve_role_empty_admins():
    from src.auth import _resolve_role
    assert _resolve_role("anyone@pg.com") == "consultor"


def test_resolve_role_no_admin_emails_env():
    import os
    os.environ.pop("ADMIN_EMAILS", None)
    from src.auth import _resolve_role
    assert _resolve_role("anyone@pg.com") == "consultor"


# ---- JWT validation with mock ----

def _make_valid_jwt_claims(email="user@pg.com"):
    return {
        "preferred_username": email,
        "name": "Test User",
        "aud": "test-client-id",
        "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
        "exp": int(time.time()) + 3600,
    }


@patch("src.auth._validate_jwt_token")
@patch.dict("os.environ", {
    "AZURE_AD_CLIENT_ID": "test-client-id",
    "AZURE_AD_TENANT_ID": "test-tenant",
})
def test_require_auth_valid_token_injects_user(mock_validate):
    mock_validate.return_value = _make_valid_jwt_claims("user@pg.com")

    from src.auth import require_auth

    user_info = None
    @require_auth
    def handler(req):
        nonlocal user_info
        user_info = getattr(req, "user", None)
        return func.HttpResponse("ok", status_code=200)

    req = _make_request(token="valid.jwt.token")
    resp = handler(req)
    assert resp.status_code == 200
    assert user_info["email"] == "user@pg.com"
    assert user_info["role"] == "consultor"


@patch("src.auth._validate_jwt_token")
@patch.dict("os.environ", {
    "AZURE_AD_CLIENT_ID": "test-client-id",
    "AZURE_AD_TENANT_ID": "test-tenant",
    "ADMIN_EMAILS": "admin@pg.com",
})
def test_require_admin_allows_admin(mock_validate):
    mock_validate.return_value = _make_valid_jwt_claims("admin@pg.com")

    from src.auth import require_admin

    @require_admin
    def handler(req):
        return func.HttpResponse("ok", status_code=200)

    req = _make_request(token="valid.jwt.token")
    resp = handler(req)
    assert resp.status_code == 200


@patch("src.auth._validate_jwt_token")
@patch.dict("os.environ", {
    "AZURE_AD_CLIENT_ID": "test-client-id",
    "AZURE_AD_TENANT_ID": "test-tenant",
    "ADMIN_EMAILS": "admin@pg.com",
})
def test_require_admin_rejects_consultor(mock_validate):
    mock_validate.return_value = _make_valid_jwt_claims("user@pg.com")

    from src.auth import require_admin

    @require_admin
    def handler(req):
        return func.HttpResponse("ok", status_code=200)

    req = _make_request(token="valid.jwt.token")
    with pytest.raises(ForbiddenError):
        handler(req)
```

**Step 2: Rodar testes — devem falhar**

Run: `python3 -m pytest tests/test_auth.py -v`
Expected: FAIL — `src.auth` não existe

**Step 3: Implementar `src/auth.py`**

```python
"""Authentication and authorization decorators for Azure Entra ID JWT."""
import os
import logging
import functools
import time
from typing import Any

import jwt
import requests
import azure.functions as func

from src.exceptions import AuthenticationError, ForbiddenError

logger = logging.getLogger(__name__)

# ---- JWKS cache ----

_jwks_cache: dict[str, Any] = {"keys": [], "fetched_at": 0}
_JWKS_TTL_SECONDS = 86400  # 24h


def _get_jwks_keys(tenant_id: str) -> list[dict]:
    """Fetch and cache JWKS public keys from Entra ID."""
    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < _JWKS_TTL_SECONDS:
        return _jwks_cache["keys"]

    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    keys = resp.json().get("keys", [])
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


def _validate_jwt_token(token: str) -> dict:
    """Validate JWT token against Entra ID public keys. Returns claims dict."""
    tenant_id = os.environ.get("AZURE_AD_TENANT_ID", "")
    client_id = os.environ.get("AZURE_AD_CLIENT_ID", "")

    if not tenant_id or not client_id:
        raise AuthenticationError("Configuração de autenticação incompleta no servidor")

    try:
        # Get the signing key
        jwks_keys = _get_jwks_keys(tenant_id)
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")

        key_data = None
        for k in jwks_keys:
            if k.get("kid") == kid:
                key_data = k
                break

        if not key_data:
            # Try refreshing JWKS (key rotation)
            _jwks_cache["fetched_at"] = 0
            jwks_keys = _get_jwks_keys(tenant_id)
            for k in jwks_keys:
                if k.get("kid") == kid:
                    key_data = k
                    break

        if not key_data:
            raise AuthenticationError("Token com chave de assinatura desconhecida")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)

        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        )
        return claims

    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token expirado")
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Token inválido: {e}")
    except Exception as e:
        if isinstance(e, AuthenticationError):
            raise
        logger.error(f"Erro na validação do token: {e}")
        raise AuthenticationError("Falha na validação do token")


def _resolve_role(email: str) -> str:
    """Resolve user role based on ADMIN_EMAILS env var."""
    admin_emails_raw = os.environ.get("ADMIN_EMAILS", "")
    if not admin_emails_raw.strip():
        return "consultor"
    admin_emails = {e.strip().lower() for e in admin_emails_raw.split(",") if e.strip()}
    return "admin" if email.strip().lower() in admin_emails else "consultor"


def _is_skip_auth_allowed() -> bool:
    """Check if auth can be skipped (only in local dev, never in Azure)."""
    if os.environ.get("SKIP_AUTH", "").lower() != "true":
        return False
    # WEBSITE_SITE_NAME only exists in Azure App Service/Functions
    if os.environ.get("WEBSITE_SITE_NAME"):
        logger.warning("SKIP_AUTH=true ignorado — detectado ambiente Azure (WEBSITE_SITE_NAME presente)")
        return False
    logger.warning("SKIP_AUTH=true — autenticação desabilitada (ambiente local)")
    return True


def _extract_and_validate(req: func.HttpRequest) -> dict:
    """Extract Bearer token, validate, and return user info dict."""
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthenticationError("Token de autenticação ausente")

    token = auth_header[7:]  # Strip "Bearer "
    claims = _validate_jwt_token(token)

    email = claims.get("preferred_username") or claims.get("email", "")
    name = claims.get("name", "")
    role = _resolve_role(email)

    return {"email": email, "name": name, "role": role, "claims": claims}


def require_auth(fn):
    """Decorator: validates JWT and injects req.user = {email, name, role, claims}."""
    @functools.wraps(fn)
    def wrapper(req: func.HttpRequest, *args, **kwargs):
        # OPTIONS bypass — preflight CORS never has auth
        if req.method == "OPTIONS":
            return fn(req, *args, **kwargs)

        if _is_skip_auth_allowed():
            req.user = {"email": "dev@local", "name": "Dev Local", "role": "admin", "claims": {}}
            return fn(req, *args, **kwargs)

        user_info = _extract_and_validate(req)
        req.user = user_info
        return fn(req, *args, **kwargs)

    return wrapper


def require_admin(fn):
    """Decorator: validates JWT + requires admin role. Composes auth internally."""
    @functools.wraps(fn)
    def wrapper(req: func.HttpRequest, *args, **kwargs):
        if req.method == "OPTIONS":
            return fn(req, *args, **kwargs)

        if _is_skip_auth_allowed():
            req.user = {"email": "dev@local", "name": "Dev Local", "role": "admin", "claims": {}}
            return fn(req, *args, **kwargs)

        user_info = _extract_and_validate(req)
        if user_info["role"] != "admin":
            raise ForbiddenError()
        req.user = user_info
        return fn(req, *args, **kwargs)

    return wrapper
```

**Step 4: Rodar testes — devem passar**

Run: `python3 -m pytest tests/test_auth.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/auth.py tests/test_auth.py
git commit -m "Adicionando módulo de autenticação JWT Entra ID (src/auth.py)"
```

---

## Task 5: Dependências Python

**Files:**
- Modify: `requirements.txt`

**Step 1: Adicionar dependências**

Ao final de `requirements.txt`:

```
PyJWT>=2.8.0
cryptography>=42.0.0
```

**Step 2: Instalar**

Run: `pip install -r requirements.txt`

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "Adicionando PyJWT e cryptography nas dependências"
```

---

## Task 6: Endpoint GetUserProfile

**Files:**
- Create: `blueprints/auth_bp.py`
- Test: `tests/test_auth_bp.py`

**Step 1: Escrever os testes**

```python
# tests/test_auth_bp.py

from unittest.mock import patch, MagicMock
import json
import azure.functions as func


def _make_request(method="GET", token="valid.token", origin="http://localhost:3000"):
    headers = {"Origin": origin}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return func.HttpRequest(
        method=method,
        url="http://localhost:7071/api/GetUserProfile",
        headers=headers,
        body=b"",
    )


@patch("src.auth._validate_jwt_token")
@patch.dict("os.environ", {
    "AZURE_AD_CLIENT_ID": "test-client-id",
    "AZURE_AD_TENANT_ID": "test-tenant",
    "ADMIN_EMAILS": "admin@pg.com",
})
def test_get_user_profile_consultor(mock_validate):
    mock_validate.return_value = {
        "preferred_username": "user@pg.com",
        "name": "Test User",
        "aud": "test-client-id",
        "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
        "exp": 9999999999,
    }

    from blueprints.auth_bp import get_user_profile_endpoint
    req = _make_request()
    resp = get_user_profile_endpoint(req)
    data = json.loads(resp.get_body())
    assert resp.status_code == 200
    assert data["email"] == "user@pg.com"
    assert data["name"] == "Test User"
    assert data["role"] == "consultor"


@patch("src.auth._validate_jwt_token")
@patch.dict("os.environ", {
    "AZURE_AD_CLIENT_ID": "test-client-id",
    "AZURE_AD_TENANT_ID": "test-tenant",
    "ADMIN_EMAILS": "admin@pg.com",
})
def test_get_user_profile_admin(mock_validate):
    mock_validate.return_value = {
        "preferred_username": "admin@pg.com",
        "name": "Admin User",
        "aud": "test-client-id",
        "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
        "exp": 9999999999,
    }

    from blueprints.auth_bp import get_user_profile_endpoint
    req = _make_request()
    resp = get_user_profile_endpoint(req)
    data = json.loads(resp.get_body())
    assert data["role"] == "admin"


def test_get_user_profile_options():
    from blueprints.auth_bp import get_user_profile_endpoint
    req = _make_request(method="OPTIONS", token=None)
    resp = get_user_profile_endpoint(req)
    assert resp.status_code == 200
    assert "Authorization" in resp.headers.get("Access-Control-Allow-Headers", "")
```

**Step 2: Rodar testes — devem falhar**

Run: `python3 -m pytest tests/test_auth_bp.py -v`

**Step 3: Implementar o blueprint**

```python
# blueprints/auth_bp.py
"""Blueprint for authentication endpoints."""
import azure.functions as func
from src.api_helpers import json_response, options_response, handle_errors
from src.auth import require_auth

auth_bp = func.Blueprint()


@auth_bp.route(route="GetUserProfile", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("GetUserProfile")
@require_auth
def get_user_profile_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetUserProfile — returns authenticated user info."""
    if req.method == "OPTIONS":
        return options_response(req)

    user = req.user
    return json_response({
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    }, request=req)
```

**Step 4: Registrar no `function_app.py`**

Adicionar import e register:
```python
from blueprints.auth_bp import auth_bp
app.register_blueprint(auth_bp)
```

**Step 5: Rodar testes — devem passar**

Run: `python3 -m pytest tests/test_auth_bp.py -v`

**Step 6: Commit**

```bash
git add blueprints/auth_bp.py tests/test_auth_bp.py function_app.py
git commit -m "Adicionando endpoint GetUserProfile com auth JWT"
```

---

## Task 7: Proteger blueprints existentes — OPTIONS + Auth decorators

**Files:**
- Modify: `blueprints/knowledge_bp.py`
- Modify: `blueprints/projects_bp.py`
- Modify: `blueprints/review_bp.py`
- Modify: `blueprints/classification_bp.py` (atualizar `options_response(req)`)
- Modify: `blueprints/models_bp.py` (atualizar `options_response(req)`)
- Modify: `blueprints/copilot_bp.py` (atualizar `options_response(req)`)

Esta é a task mais volumosa. O padrão para cada endpoint é:

### Padrão para `@require_auth` endpoints:

```python
@bp.route(route="EndpointName", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("EndpointName")
@require_auth
def endpoint_name(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return options_response(req)
    # ... lógica existente ...
```

### Padrão para `@require_admin` endpoints:

```python
@bp.route(route="EndpointName", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("EndpointName")
@require_admin
def endpoint_name(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return options_response(req)
    # ... lógica existente ...
```

### Mudanças por blueprint:

**`knowledge_bp.py`** — adicionar imports: `from src.auth import require_auth, require_admin` e `from src.api_helpers import options_response`

| Endpoint | Methods atuais | Adicionar OPTIONS | Decorator |
|----------|---------------|-------------------|-----------|
| GetKnowledgeBase | GET | + OPTIONS | `@require_auth` |
| AddKBEntry | POST | + OPTIONS | `@require_auth` |
| UpdateKBEntry | PUT | + OPTIONS | `@require_auth` |
| DeleteKBEntry | DELETE | + OPTIONS | `@require_auth` |
| GetKBCoverage | GET | + OPTIONS | `@require_auth` |
| GetKBVersions | GET | + OPTIONS | `@require_auth` |
| RollbackKB | POST | + OPTIONS | `@require_auth` |
| ExportKB | GET | + OPTIONS | `@require_auth` |
| ImportKB | POST | + OPTIONS | `@require_auth` |
| GetSectorKB | GET | + OPTIONS | `@require_auth` |
| GetSectorKBCoverage | GET | + OPTIONS | `@require_auth` |
| GetSectorKBVersions | GET | + OPTIONS | `@require_auth` |
| ExportSectorKB | GET | + OPTIONS | `@require_auth` |
| **ImportSectorKB** | POST | + OPTIONS | **`@require_admin`** |
| **UpdateSectorKBEntry** | PUT | + OPTIONS | **`@require_admin`** |
| **DeleteSectorKBEntry** | DELETE | + OPTIONS | **`@require_admin`** |
| **RollbackSectorKB** | POST | + OPTIONS | **`@require_admin`** |
| **AddSectorKBEntry** | POST | + OPTIONS | **`@require_admin`** |
| **PromoteToSectorKB** | POST | + OPTIONS | **`@require_admin`** |

**`projects_bp.py`** — adicionar imports: `from src.auth import require_auth, require_admin` e `from src.api_helpers import options_response`

| Endpoint | Adicionar OPTIONS | Decorator |
|----------|-------------------|-----------|
| ListSectors | + OPTIONS | `@require_auth` |
| **CreateSector** | + OPTIONS | **`@require_admin`** |
| **UpdateSector** | + OPTIONS | **`@require_admin`** |
| **DeleteSector** | + OPTIONS | **`@require_admin`** |
| ListProjects | + OPTIONS | `@require_auth` |
| CreateProject | + OPTIONS | `@require_auth` |
| UpdateProject | + OPTIONS | `@require_auth` |
| DeleteProject | + OPTIONS | `@require_auth` |
| GetProjectHierarchy | + OPTIONS | `@require_auth` |

**`review_bp.py`** — adicionar imports: `from src.auth import require_auth` e `from src.api_helpers import options_response`

| Endpoint | Adicionar OPTIONS | Decorator |
|----------|-------------------|-----------|
| ReclassifyItems | + OPTIONS | `@require_auth` |
| ApproveClassifications | + OPTIONS | `@require_auth` |

**`classification_bp.py`** — já tem OPTIONS nos endpoints. Adicionar `from src.auth import require_auth`, e `@require_auth` entre `@handle_errors` e a função. Atualizar `options_response()` → `options_response(req)`.

**`models_bp.py`** — já tem OPTIONS. Adicionar `@require_auth`. Atualizar `options_response()` → `options_response(req)`.

**`copilot_bp.py`** — já tem OPTIONS. Adicionar `@require_auth`. Atualizar `options_response()` → `options_response(req)`.

**`health_bp.py`** — NÃO adicionar auth (health check livre).

**`worker_bp.py`** — NÃO adicionar auth (timer trigger, não é HTTP).

**Step 1: Fazer as mudanças em todos os blueprints**

(Aplicar o padrão descrito acima em cada blueprint)

**Step 2: Rodar todos os testes do backend**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (testes existentes podem precisar de ajustes se mockam endpoints diretamente — adicionar `SKIP_AUTH=true` no patch de env)

**Nota sobre testes existentes:** Testes que chamam endpoints diretamente precisarão de `@patch.dict("os.environ", {"SKIP_AUTH": "true"})` para bypassar auth. Identificar e ajustar conforme necessário.

**Step 3: Commit**

```bash
git add blueprints/
git commit -m "Adicionando auth decorators e OPTIONS em todos os blueprints"
```

---

## Task 8: Variáveis de ambiente — config files

**Files:**
- Modify: `local.settings.json.example`
- Modify: `frontend/.env.local.example`

**Step 1: Atualizar `local.settings.json.example`**

Adicionar ao objeto `Values`:
```json
"AZURE_AD_TENANT_ID": "",
"AZURE_AD_CLIENT_ID": "",
"ADMIN_EMAILS": "",
"SKIP_AUTH": "true",
"ALLOWED_ORIGINS": "http://localhost:3000"
```

**Step 2: Atualizar `frontend/.env.local.example`**

Adicionar:
```
NEXT_PUBLIC_AZURE_AD_CLIENT_ID=
NEXT_PUBLIC_AZURE_AD_TENANT_ID=
```

Remover (ou comentar):
```
# NEXT_PUBLIC_FUNCTION_KEY=  (substituído por auth JWT)
```

**Step 3: Commit**

```bash
git add local.settings.json.example frontend/.env.local.example
git commit -m "Adicionando variáveis de auth nos arquivos de exemplo"
```

---

## Task 9: Frontend — MSAL config e AuthContext

**Files:**
- Create: `frontend/src/lib/msal-config.ts`
- Create: `frontend/src/contexts/AuthContext.tsx`

**Step 1: Instalar dependências**

Run: `cd frontend && npm install @azure/msal-browser@^3 @azure/msal-react@^2`

**Step 2: Criar MSAL config**

```typescript
// frontend/src/lib/msal-config.ts
import { Configuration, LogLevel } from '@azure/msal-browser';

const clientId = process.env.NEXT_PUBLIC_AZURE_AD_CLIENT_ID || '';
const tenantId = process.env.NEXT_PUBLIC_AZURE_AD_TENANT_ID || '';

export const msalConfig: Configuration = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: typeof window !== 'undefined' ? window.location.origin : '',
    postLogoutRedirectUri: typeof window !== 'undefined' ? window.location.origin : '',
  },
  cache: {
    cacheLocation: 'sessionStorage',
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
    },
  },
};

export const loginRequest = {
  scopes: ['User.Read'],
};
```

**Step 3: Criar AuthContext**

```typescript
// frontend/src/contexts/AuthContext.tsx
import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useMsal, useIsAuthenticated } from '@azure/msal-react';
import { InteractionStatus } from '@azure/msal-browser';
import { loginRequest } from '@/lib/msal-config';
import { apiClient } from '@/lib/api';

interface User {
  email: string;
  name: string;
  role: 'admin' | 'consultor';
}

interface AuthContextType {
  user: User | null;
  isAdmin: boolean;
  isLoading: boolean;
  getAccessToken: () => Promise<string>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAdmin: false,
  isLoading: true,
  getAccessToken: async () => '',
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const getAccessToken = useCallback(async (): Promise<string> => {
    if (!accounts[0]) return '';
    try {
      const result = await instance.acquireTokenSilent({
        ...loginRequest,
        account: accounts[0],
      });
      return result.accessToken;
    } catch {
      // Silent token failed — try interactive
      const result = await instance.acquireTokenPopup(loginRequest);
      return result.accessToken;
    }
  }, [instance, accounts]);

  const logout = useCallback(() => {
    instance.logoutRedirect();
  }, [instance]);

  useEffect(() => {
    if (inProgress !== InteractionStatus.None) return;

    if (!isAuthenticated) {
      instance.loginRedirect(loginRequest);
      return;
    }

    // Fetch user profile from backend
    const fetchProfile = async () => {
      try {
        const token = await getAccessToken();
        const profile = await apiClient.getUserProfile(token);
        setUser(profile);
      } catch (err) {
        console.error('Failed to fetch user profile:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfile();
  }, [isAuthenticated, inProgress, instance, getAccessToken]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAdmin: user?.role === 'admin',
        isLoading,
        getAccessToken,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
```

**Step 4: Commit**

```bash
cd frontend
git add src/lib/msal-config.ts src/contexts/AuthContext.tsx
git commit -m "Adicionando MSAL config e AuthContext para autenticação Entra ID"
```

---

## Task 10: Frontend — Atualizar `api.ts` para usar Bearer token

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Step 1: Refatorar `getAuthHeaders` e adicionar `getUserProfile`**

Mudanças em `api.ts`:

1. Remover `FUNCTION_KEY` e `getAuthHeaders()`
2. Adicionar variável de módulo `_getToken: (() => Promise<string>) | null = null`
3. Adicionar `setTokenProvider(fn)` para injeção do token provider
4. Substituir todas as `getAuthHeaders()` por chamada assíncrona ao token provider
5. Adicionar método `getUserProfile(token)`

```typescript
// No topo, substituir:
// const FUNCTION_KEY = ...
// const getAuthHeaders = ...

// Por:
let _getToken: (() => Promise<string>) | null = null;

export function setTokenProvider(fn: () => Promise<string>) {
  _getToken = fn;
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  if (!_getToken) return {};
  try {
    const token = await _getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}
```

Todas as chamadas `{ headers: getAuthHeaders() }` mudam para `{ headers: await getAuthHeaders() }`.

Adicionar método no `apiClient`:

```typescript
async getUserProfile(token?: string): Promise<{ email: string; name: string; role: 'admin' | 'consultor' }> {
  const headers = token
    ? { Authorization: `Bearer ${token}` }
    : await getAuthHeaders();
  const response = await axios.get(`${API_BASE_URL}/GetUserProfile`, { headers });
  return response.data;
},
```

**Step 2: Rodar testes frontend**

Run: `cd frontend && npx jest --verbose`
Expected: Testes existentes de `api.ts` podem precisar de ajuste no mock de `getAuthHeaders` (agora async)

**Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "Ajuste api.ts: Bearer token via token provider, remove x-functions-key"
```

---

## Task 11: Frontend — Atualizar `_app.tsx` com MsalProvider + AuthGuard

**Files:**
- Modify: `frontend/src/pages/_app.tsx`

**Step 1: Implementar**

```typescript
// frontend/src/pages/_app.tsx
import '@/styles/globals.css';
import type { AppProps } from 'next/app';
import { useEffect, useState } from 'react';
import { PublicClientApplication, EventType } from '@azure/msal-browser';
import { MsalProvider } from '@azure/msal-react';
import { msalConfig } from '@/lib/msal-config';
import { AuthProvider } from '@/contexts/AuthContext';

const msalInstance = new PublicClientApplication(msalConfig);

// Handle redirect callback
msalInstance.initialize().then(() => {
  const accounts = msalInstance.getAllAccounts();
  if (accounts.length > 0) {
    msalInstance.setActiveAccount(accounts[0]);
  }

  msalInstance.addEventCallback((event) => {
    if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
      const payload = event.payload as { account: any };
      msalInstance.setActiveAccount(payload.account);
    }
  });
});

function AuthGuard({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

function LoadingScreen() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4" />
        <p className="text-gray-600">Autenticando...</p>
      </div>
    </div>
  );
}

export default function App({ Component, pageProps }: AppProps) {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    msalInstance.initialize().then(() => setIsReady(true));
  }, []);

  if (!isReady) return <LoadingScreen />;

  return (
    <MsalProvider instance={msalInstance}>
      <AuthGuard>
        <Component {...pageProps} />
      </AuthGuard>
    </MsalProvider>
  );
}
```

**Step 2: Conectar token provider ao api.ts**

No `AuthContext.tsx`, após configurar o token provider:

```typescript
// No useEffect após autenticação, antes de fetchProfile:
import { setTokenProvider } from '@/lib/api';
// ...
setTokenProvider(getAccessToken);
```

**Step 3: Build para verificar TypeScript**

Run: `cd frontend && npm run build`
Expected: Build sem erros

**Step 4: Commit**

```bash
git add frontend/src/pages/_app.tsx frontend/src/contexts/AuthContext.tsx
git commit -m "Adicionando MsalProvider e AuthGuard no _app.tsx"
```

---

## Task 12: Frontend — UI condicional para admin

**Files:**
- Modify: componentes que exibem ações de setor KB

**Step 1: Identificar pontos de UI a proteger**

Usar `useAuth()` nos componentes e condicionar ações admin:

```typescript
import { useAuth } from '@/contexts/AuthContext';

// Dentro do componente:
const { isAdmin } = useAuth();

// Condicionar botões:
{isAdmin && <Button onClick={handlePromote}>Promover para KB do Setor</Button>}
```

Componentes a modificar:
- `SectorKnowledgeTab` — botões de import, edit, delete, rollback, add
- `KnowledgeTab` ou `KBPanel` — botão de promoção para setor
- `CollapsibleSidebar` ou local que cria/deleta setores

**Step 2: Adicionar indicador de usuário no header**

No `ContextBar` ou header, adicionar:

```typescript
const { user, isAdmin, logout } = useAuth();
// Exibir: nome, badge "Admin"/"Consultor", botão logout
```

**Step 3: Build e verificar**

Run: `cd frontend && npm run build`

**Step 4: Commit**

```bash
git add frontend/src/
git commit -m "Adicionando UI condicional para admin e indicador de usuário"
```

---

## Task 13: Testes — ajustar testes existentes

**Files:**
- Modify: `tests/` (múltiplos arquivos)

**Step 1: Adicionar SKIP_AUTH nos testes de blueprint**

Testes existentes que chamam endpoints diretamente precisam de:

```python
@patch.dict("os.environ", {"SKIP_AUTH": "true"})
def test_existing_endpoint(...):
    ...
```

Ou, melhor: criar um fixture/conftest:

```python
# tests/conftest.py — adicionar
import os

@pytest.fixture(autouse=True)
def skip_auth_for_tests(monkeypatch):
    """Bypass auth in all tests by default."""
    monkeypatch.setenv("SKIP_AUTH", "true")
    monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)
```

**Step 2: Rodar todos os testes**

Run: `python3 -m pytest tests/ -v`
Expected: 267+ passed

Run: `cd frontend && npx jest --verbose`
Expected: 50+ passed

**Step 3: Commit**

```bash
git add tests/
git commit -m "Ajuste testes: SKIP_AUTH fixture para bypassar auth nos testes"
```

---

## Task 14: Verificação final e cleanup

**Step 1: Rodar todos os testes backend**

Run: `python3 -m pytest tests/ -v`

**Step 2: Rodar todos os testes frontend**

Run: `cd frontend && npx jest --verbose`

**Step 3: Build frontend**

Run: `cd frontend && npm run build`

**Step 4: Testar manualmente (local)**

1. Configurar `AZURE_AD_TENANT_ID` e `AZURE_AD_CLIENT_ID` em `local.settings.json`
2. Configurar `NEXT_PUBLIC_AZURE_AD_CLIENT_ID` e `NEXT_PUBLIC_AZURE_AD_TENANT_ID` em `frontend/.env.local`
3. `func start` e `cd frontend && npm run dev`
4. Acessar `http://localhost:3000` — deve redirecionar para login Microsoft
5. Após login, verificar que o app carrega normalmente
6. Verificar `GetUserProfile` retorna email e role corretos
7. Se admin: verificar que botões de KB do setor aparecem
8. Se consultor: verificar que botões de KB do setor NÃO aparecem

**Step 5: Commit final se necessário**

```bash
git add .
git commit -m "Ajustes finais de autenticação Entra ID"
```
