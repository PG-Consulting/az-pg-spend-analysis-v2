# Security Quick Wins — 7 Correções de Endurecimento

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir 7 vulnerabilidades de segurança sem custo, identificadas pelo pentest e production readiness review.

**Architecture:** Todas as mudanças são defensivas — validação de input, headers HTTP, restrição de info. Nenhuma muda o comportamento funcional do produto. Padrão: função centralizada reutilizada por todos os blueprints.

**Tech Stack:** Python 3.12 (Azure Functions), Next.js 14 (Azure Static Web Apps), pytest

---

## Mapa de Arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `src/validation.py` | **Criar** | `safe_resource_id()` — validação centralizada contra path traversal |
| `src/auth.py` | Modificar | Group claim: bloquear em vez de ignorar. JWT: mensagens genéricas |
| `src/api_helpers.py` | Modificar | Security headers em `_cors_headers()` |
| `blueprints/health_bp.py` | Modificar | Health público mínimo, detalhes só para admin |
| `blueprints/knowledge_bp.py` | Modificar | Aplicar `safe_resource_id` em todos os 20+ pontos de extração de IDs |
| `blueprints/projects_bp.py` | Modificar | Aplicar `safe_resource_id` em sectorName e projectId |
| `blueprints/classification_bp.py` | Modificar | Aplicar `safe_resource_id` em projectId, jobId e sector |
| `blueprints/review_bp.py` | Modificar | Aplicar `safe_resource_id` em jobId e projectId |
| `blueprints/models_bp.py` | Modificar | Aplicar `safe_resource_id` em sector e version_id |
| `frontend/staticwebapp.config.json` | Modificar | X-Frame-Options, desabilitar GitHub auth |
| `tests/test_validation.py` | **Criar** | Testes para `safe_resource_id` |
| `tests/test_auth.py` | Modificar | Atualizar teste do group claim + adicionar testes de mensagens genéricas |
| `tests/test_api_helpers.py` | Modificar | Verificar security headers |
| `tests/test_health.py` | Modificar | Atualizar 5 testes existentes para SKIP_AUTH + adicionar teste de resposta pública |

---

## Task 1: HTTPS Only no Azure Portal

**Files:** Nenhum arquivo de código — configuração no Azure Portal.

- [ ] **Step 1: Habilitar HTTPS Only via Azure CLI**

```bash
az functionapp update \
  --name az-pg-spend-analysis-ai-agent \
  --resource-group azpgspendanalysisaiagent \
  --set httpsOnly=true
```

- [ ] **Step 2: Verificar que HTTP redireciona para HTTPS**

```bash
curl -s -o /dev/null -w "%{http_code}" "http://az-pg-spend-analysis-ai-agent.azurewebsites.net/api/health"
# Esperado: 301 (redirect para HTTPS)
```

- [ ] **Step 3: Verificar que HTTPS continua funcionando**

```bash
curl -s "https://az-pg-spend-analysis-ai-agent.azurewebsites.net/api/health" | python3 -m json.tool
# Esperado: {"status": "healthy", ...}
```

---

## Task 2: Sanitizar IDs contra path traversal

**Files:**
- Criar: `src/validation.py`
- Criar: `tests/test_validation.py`
- Modificar: `blueprints/knowledge_bp.py` (import topo + 20 pontos)
- Modificar: `blueprints/projects_bp.py` (import topo + 4 pontos)
- Modificar: `blueprints/classification_bp.py` (import topo + 6 pontos)
- Modificar: `blueprints/review_bp.py` (import topo + 4 pontos)
- Modificar: `blueprints/models_bp.py` (import topo + 7 pontos)

- [ ] **Step 1: Escrever os testes de validação**

Criar `tests/test_validation.py`:

```python
"""Tests for src/validation.py — input sanitization."""

import pytest

from src.validation import safe_resource_id
from src.exceptions import ValidationError


class TestSafeResourceId:
    def test_valid_simple_id(self):
        assert safe_resource_id("naval-wartsila") == "naval-wartsila"

    def test_valid_uuid(self):
        assert safe_resource_id("a1b2c3d4-e5f6-7890-abcd-ef1234567890") == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_strips_whitespace(self):
        assert safe_resource_id("  naval  ") == "naval"

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            safe_resource_id("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValidationError):
            safe_resource_id("   ")

    def test_rejects_none(self):
        with pytest.raises(ValidationError):
            safe_resource_id(None)

    def test_rejects_dot_dot(self):
        with pytest.raises(ValidationError):
            safe_resource_id("../secrets")

    def test_rejects_dot_dot_in_middle(self):
        with pytest.raises(ValidationError):
            safe_resource_id("project/../secrets")

    def test_rejects_forward_slash(self):
        with pytest.raises(ValidationError):
            safe_resource_id("project/subdir")

    def test_rejects_backslash(self):
        with pytest.raises(ValidationError):
            safe_resource_id("project\\subdir")

    def test_rejects_null_byte(self):
        with pytest.raises(ValidationError):
            safe_resource_id("project\x00evil")

    def test_rejects_oversized_input(self):
        with pytest.raises(ValidationError):
            safe_resource_id("a" * 257)

    def test_custom_field_name_in_error(self):
        with pytest.raises(ValidationError, match="jobId"):
            safe_resource_id("", field="jobId")

    def test_allows_dots_without_traversal(self):
        assert safe_resource_id("v1.0") == "v1.0"

    def test_allows_underscores(self):
        assert safe_resource_id("my_project_123") == "my_project_123"

    def test_max_length_boundary(self):
        assert safe_resource_id("a" * 256) == "a" * 256
```

- [ ] **Step 2: Rodar testes — confirmar que falham**

```bash
python3 -m pytest tests/test_validation.py -v
# Esperado: FAIL — ModuleNotFoundError: No module named 'src.validation'
```

- [ ] **Step 3: Implementar safe_resource_id**

Criar `src/validation.py`:

```python
"""Input validation utilities — centralised sanitisation for resource identifiers."""

from src.exceptions import ValidationError

_MAX_ID_LENGTH = 256


def safe_resource_id(value, field: str = "identifier") -> str:
    """Sanitise a resource identifier (projectId, sectorName, jobId, entryId).

    Prevents path traversal, null byte injection, and oversized inputs.
    Raises ValidationError if the value is empty or contains forbidden characters.
    """
    if value is None:
        value = ""
    sanitized = str(value).strip()
    if not sanitized:
        raise ValidationError(f"Missing required field: {field}", field=field)
    if len(sanitized) > _MAX_ID_LENGTH:
        raise ValidationError(f"Invalid {field}: exceeds maximum length", field=field)
    if ".." in sanitized or "/" in sanitized or "\\" in sanitized or "\x00" in sanitized:
        raise ValidationError(f"Invalid {field}: contains forbidden characters", field=field)
    return sanitized
```

- [ ] **Step 4: Rodar testes — confirmar que passam**

```bash
python3 -m pytest tests/test_validation.py -v
# Esperado: 16 passed
```

- [ ] **Step 5: Aplicar safe_resource_id nos blueprints**

**IMPORTANTE:** Ao adicionar `safe_resource_id`, **remover** as checagens duplicadas de empty que existem logo abaixo (ex: `if not project_id: raise ValidationError(...)`) — `safe_resource_id` já valida isso.

**`blueprints/knowledge_bp.py`** — import no topo (junto dos outros `from src.*`):
```python
from src.validation import safe_resource_id
```

Pontos de extração a substituir (todos os `.strip()` são absorvidos por `safe_resource_id`):

| Linha | De | Para |
|-------|-----|------|
| 23 | `return req.params.get("projectId", "").strip()` | `return safe_resource_id(req.params.get("projectId", ""), field="projectId")` |
| 83 | `project_id = body.get("projectId", "").strip()` | `project_id = safe_resource_id(body.get("projectId", ""), field="projectId")` |
| 130 | `project_id = body.get("projectId", "").strip()` | `project_id = safe_resource_id(body.get("projectId", ""), field="projectId")` |
| 131 | `entry_id = body.get("entryId", "").strip()` | `entry_id = safe_resource_id(body.get("entryId", ""), field="entryId")` |
| 178 | `project_id = req.params.get("projectId", "").strip()` | `project_id = safe_resource_id(req.params.get("projectId", ""), field="projectId")` |
| 179 | `entry_id = req.params.get("entryId", "").strip()` | `entry_id = safe_resource_id(req.params.get("entryId", ""), field="entryId")` |
| 296 | `project_id = body.get("projectId", "").strip()` | `project_id = safe_resource_id(body.get("projectId", ""), field="projectId")` |
| 297 | `version_id = body.get("versionId", "").strip()` | `version_id = safe_resource_id(body.get("versionId", ""), field="versionId")` |
| 360 | `project_id = body.get("projectId", "").strip()` | `project_id = safe_resource_id(body.get("projectId", ""), field="projectId")` |
| 388 | `return req.params.get("sectorName", "").strip().lower()` | `return safe_resource_id(req.params.get("sectorName", ""), field="sectorName").lower()` |
| 531 | `sector_name = body.get("sectorName", "").strip().lower()` | `sector_name = safe_resource_id(body.get("sectorName", ""), field="sectorName").lower()` |
| 569 | `sector_name = body.get("sectorName", "").strip().lower()` | `sector_name = safe_resource_id(body.get("sectorName", ""), field="sectorName").lower()` |
| 570 | `entry_id = body.get("entryId", "").strip()` | `entry_id = safe_resource_id(body.get("entryId", ""), field="entryId")` |
| 616 | `sector_name = req.params.get("sectorName", "").strip().lower()` | `sector_name = safe_resource_id(req.params.get("sectorName", ""), field="sectorName").lower()` |
| 617 | `entry_id = req.params.get("entryId", "").strip()` | `entry_id = safe_resource_id(req.params.get("entryId", ""), field="entryId")` |
| 648 | `sector_name = body.get("sectorName", "").strip().lower()` | `sector_name = safe_resource_id(body.get("sectorName", ""), field="sectorName").lower()` |
| 649 | `version_id = body.get("versionId", "").strip()` | `version_id = safe_resource_id(body.get("versionId", ""), field="versionId")` |
| 680 | `sector_name = body.get("sectorName", "").strip().lower()` | `sector_name = safe_resource_id(body.get("sectorName", ""), field="sectorName").lower()` |
| 727 | `project_id = body.get("projectId", "").strip()` | `project_id = safe_resource_id(body.get("projectId", ""), field="projectId")` |
| 728 | `sector_name = body.get("sectorName", "").strip().lower()` | `sector_name = safe_resource_id(body.get("sectorName", ""), field="sectorName").lower()` |

**`blueprints/projects_bp.py`** — import no topo:
```python
from src.validation import safe_resource_id
```

| Linha | De | Para |
|-------|-----|------|
| 97 | `sector_name = req.params.get("sectorName", "").strip()` | `sector_name = safe_resource_id(req.params.get("sectorName", ""), field="sectorName")` |
| 162 | `project_id = body.get("project_id", "").strip()` | `project_id = safe_resource_id(body.get("project_id", ""), field="projectId")` |
| 182 | `project_id = req.params.get("projectId", "").strip()` | `project_id = safe_resource_id(req.params.get("projectId", ""), field="projectId")` |
| 203 | `project_id = req.params.get("projectId", "").strip()` | `project_id = safe_resource_id(req.params.get("projectId", ""), field="projectId")` |

**`blueprints/classification_bp.py`** — import no topo:
```python
from src.validation import safe_resource_id
```

| Linha | De | Para |
|-------|-----|------|
| 100 | `project_id = req_body.get("projectId", "").strip()` | `project_id = safe_resource_id(req_body.get("projectId", ""), field="projectId")` |
| 127 | `sector_raw = req_body.get("sector")` | `sector_raw = safe_resource_id(req_body.get("sector", ""), field="sector")` |
| 283 | `job_id = req.params.get("jobId")` | `job_id = safe_resource_id(req.params.get("jobId", ""), field="jobId")` |
| 346 | `job_id = req.params.get("jobId")` | `job_id = safe_resource_id(req.params.get("jobId", ""), field="jobId")` |
| 390 | `job_id = req.params.get("jobId", "").strip()` | `job_id = safe_resource_id(req.params.get("jobId", ""), field="jobId")` |
| 513 | `job_id = req.params.get("jobId", "").strip()` | `job_id = safe_resource_id(req.params.get("jobId", ""), field="jobId")` |

**Nota linha 127-130:** Atualmente é:
```python
sector_raw = req_body.get("sector")
if not sector_raw:
    raise ValidationError("Missing projectId or sector")
sector = sector_raw.strip().capitalize()
```
Substituir por:
```python
sector = safe_resource_id(req_body.get("sector", ""), field="sector").capitalize()
```
(Remove a checagem duplicada `if not sector_raw` e o `.strip()`)

**`blueprints/review_bp.py`** — import no topo:
```python
from src.validation import safe_resource_id
```

| Linha | De | Para |
|-------|-----|------|
| 48 | `job_id = body.get("jobId", "")` | `job_id = safe_resource_id(body.get("jobId", ""), field="jobId")` |
| 51 | `project_id = body.get("projectId", "")` | `project_id = safe_resource_id(body.get("projectId", ""), field="projectId")` |
| 175 | `job_id = body.get("jobId", "")` | `job_id = safe_resource_id(body.get("jobId", ""), field="jobId")` |
| 178 | `project_id = body.get("projectId", "")` | `project_id = safe_resource_id(body.get("projectId", ""), field="projectId")` |

Remover as checagens `if not job_id:` e `if not project_id:` que existem logo depois (linhas 49-50, 52-53, 176-177, 179-180).

**`blueprints/models_bp.py`** — import no topo:
```python
from src.validation import safe_resource_id
```

| Linha | De | Para |
|-------|-----|------|
| 130 | `sector = body.get("sector")` | `sector = safe_resource_id(body.get("sector", ""), field="sector")` |
| 330 | `sector = req.params.get("sector")` | `sector = safe_resource_id(req.params.get("sector", ""), field="sector")` |
| 363 | `sector = req_body.get("sector")` | `sector = safe_resource_id(req_body.get("sector", ""), field="sector")` |
| 429 | `sector = req.params.get("sector")` | `sector = safe_resource_id(req.params.get("sector", ""), field="sector")` |
| 430 | `version_id = req.params.get("version_id")` | `version_id = safe_resource_id(req.params.get("version_id", ""), field="version_id")` |
| 597 | `sector = req.params.get("sector")` | `sector = safe_resource_id(req.params.get("sector", ""), field="sector")` |
| 691 | `sector = body.get("sector")` | `sector = safe_resource_id(body.get("sector", ""), field="sector")` |

Remover checagens `if not sector:` que existam logo depois.

- [ ] **Step 6: Rodar suíte completa**

```bash
python3 -m pytest tests/ -v --tb=short
# Esperado: todos os testes existentes passam (nenhum envia ../ nos IDs)
```

- [ ] **Step 7: Commit**

```bash
git add src/validation.py tests/test_validation.py blueprints/
git commit -m "Fix: sanitização de IDs contra path traversal em todos os blueprints"
```

---

## Task 3: Group claim — bloquear quando token não contém claim groups

**Files:**
- Modificar: `src/auth.py:139-143`
- Modificar: `tests/test_auth.py:85-90`

- [ ] **Step 1: Atualizar o teste existente**

Em `tests/test_auth.py`, classe `TestValidateGroupClaim`, substituir o teste `test_group_required_but_no_groups_claim` (linha 85-90):

De:
```python
    def test_group_required_but_no_groups_claim(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_GROUP_ID", "group-123")
        from src.auth import _validate_group_claim

        # Should NOT raise — IdP not configured to emit groups
        _validate_group_claim({"preferred_username": "user@test.com"})
```

Para:
```python
    def test_group_required_but_no_groups_claim(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_GROUP_ID", "group-123")
        from src.auth import _validate_group_claim

        # MUST raise — token without groups claim is not trusted
        with pytest.raises(ForbiddenError):
            _validate_group_claim({"preferred_username": "user@test.com"})
```

- [ ] **Step 2: Rodar teste — confirmar que falha**

```bash
python3 -m pytest tests/test_auth.py::TestValidateGroupClaim::test_group_required_but_no_groups_claim -v
# Esperado: FAIL — did not raise ForbiddenError
```

- [ ] **Step 3: Corrigir _validate_group_claim**

Em `src/auth.py`, substituir linhas 139-143:

De:
```python
    groups = claims.get("groups", [])
    if not groups:
        # groups claim not present — IdP not configured to emit it
        logger.warning("ALLOWED_GROUP_ID set but token has no 'groups' claim")
        return
```

Para:
```python
    groups = claims.get("groups", [])
    if not groups:
        logger.warning("ALLOWED_GROUP_ID set but token has no 'groups' claim — blocking access")
        raise ForbiddenError("Token missing required group membership claim")
```

- [ ] **Step 4: Rodar testes de auth**

```bash
python3 -m pytest tests/test_auth.py -v
# Esperado: 18 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/auth.py tests/test_auth.py
git commit -m "Fix: group claim bloqueia acesso quando token não contém claim groups"
```

---

## Task 4: Health endpoint — info mínima sem auth, detalhes para admin

**Files:**
- Modificar: `blueprints/health_bp.py:68-97`
- Modificar: `tests/test_health.py` (5 testes existentes + 1 novo)

- [ ] **Step 1: Adicionar teste para resposta pública mínima**

Em `tests/test_health.py`, adicionar na classe `TestHealthCheck`:

```python
    def test_public_returns_minimal_info(self):
        """Health endpoint without auth returns only status and version."""
        with patch.dict(os.environ, {}, clear=False):
            # Ensure SKIP_AUTH is not set
            env = {k: v for k, v in os.environ.items() if k != "SKIP_AUTH"}
            with patch.dict(os.environ, env, clear=True):
                resp = HealthCheck(_MockHttpRequest())

        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        assert body == {"status": "healthy", "version": "3.0"}
        assert "checks" not in body
```

- [ ] **Step 2: Atualizar os 5 testes existentes para usar SKIP_AUTH=true**

Todos os testes que verificam `checks` precisam rodar com `SKIP_AUTH=true` (para que `show_details=True`). Adicionar `patch.dict(os.environ, {"SKIP_AUTH": "true"})` como wrapper em cada um. Exemplo para `test_returns_200_with_expected_fields`:

```python
    @patch(
        "blueprints.health_bp._probe_grok_api",
        return_value={"reachable": True, "latency_ms": 50},
    )
    def test_returns_200_with_expected_fields(self, mock_probe, tmp_path):
        """Health endpoint returns 200 with status, version, and checks (admin)."""
        models_dir = str(tmp_path / "models")
        os.makedirs(models_dir)

        with patch("blueprints.health_bp.get_models_dir", return_value=models_dir):
            with patch.dict(os.environ, {"GROK_API_KEY": "test-key-123", "SKIP_AUTH": "true"}):
                resp = HealthCheck(_MockHttpRequest())

        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        assert body["status"] == "healthy"
        assert body["version"] == "3.0"
        assert body["checks"]["filesystem"] is True
        assert body["checks"]["grok_api_configured"] is True
        assert body["checks"]["grok_api_reachable"] is True
        assert body["checks"]["grok_api_latency_ms"] == 50
        assert body["checks"]["models_dir_configured"] is True
```

Aplicar o mesmo padrão para:
- `test_degraded_when_models_dir_missing`: adicionar `"SKIP_AUTH": "true"` no `patch.dict`
- `test_cors_headers`: adicionar `patch.dict(os.environ, {"SKIP_AUTH": "true"})` como wrapper
- `test_healthy_when_grok_reachable` e `test_degraded_when_grok_unreachable`: adicionar `"SKIP_AUTH": "true"` no env mock

**Importante:** Garantir que `WEBSITE_SITE_NAME` NÃO esteja setada nesses testes (caso contrário, `_is_skip_auth_allowed()` retorna `False` mesmo com `SKIP_AUTH=true`). Usar `monkeypatch.delenv("WEBSITE_SITE_NAME", raising=False)` ou `patch.dict(os.environ, ..., clear=True)`.

- [ ] **Step 3: Modificar HealthCheck**

Em `blueprints/health_bp.py`, substituir a função `HealthCheck` (linhas 68-97):

```python
@health_bp.route(route="health", methods=["GET"])
@handle_errors("HealthCheck")
def HealthCheck(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/health — returns service status.

    Public: minimal status only.
    Authenticated admin (or SKIP_AUTH dev): full diagnostic checks.
    """
    from src.auth import _is_skip_auth_allowed, _extract_and_validate
    from src.exceptions import AuthenticationError, ForbiddenError

    # Determine if caller is authenticated admin
    show_details = False
    if _is_skip_auth_allowed():
        show_details = True
    else:
        try:
            user = _extract_and_validate(req)
            show_details = user.get("role") == "admin"
        except (AuthenticationError, ForbiddenError):
            pass  # Not authenticated or not authorized — show public response

    if not show_details:
        return json_response({"status": "healthy", "version": "3.0"})

    # Full diagnostics for admin
    models_dir = get_models_dir()
    grok_probe = _probe_grok_api()

    checks = {
        "filesystem": os.path.isdir(models_dir),
        "grok_api_configured": bool(os.environ.get("GROK_API_KEY")),
        "grok_api_reachable": grok_probe["reachable"],
        "grok_api_latency_ms": grok_probe["latency_ms"],
        "models_dir_configured": bool(models_dir),
    }

    if not checks["filesystem"] or not checks["grok_api_reachable"]:
        status = "degraded"
    else:
        status = "healthy"

    return json_response({"status": status, "version": "3.0", "checks": checks})
```

**Nota:** Usa `except (AuthenticationError, ForbiddenError)` — NÃO `except Exception` (evita engolir bugs silenciosamente).

- [ ] **Step 4: Rodar testes**

```bash
python3 -m pytest tests/test_health.py -v
# Esperado: 6 passed (5 existentes atualizados + 1 novo)
```

- [ ] **Step 5: Commit**

```bash
git add blueprints/health_bp.py tests/test_health.py
git commit -m "Fix: health endpoint retorna info mínima sem auth, detalhes só para admin"
```

---

## Task 5: X-Frame-Options + desabilitar GitHub auth no SWA

**Files:**
- Modificar: `frontend/staticwebapp.config.json`

- [ ] **Step 1: Atualizar staticwebapp.config.json**

Substituir conteúdo de `frontend/staticwebapp.config.json`:

```json
{
    "navigationFallback": {
        "rewrite": "/index.html"
    },
    "routes": [
        {
            "route": "/api/*",
            "allowedRoles": [
                "authenticated"
            ]
        },
        {
            "route": "/.auth/login/github",
            "statusCode": 404
        },
        {
            "route": "/.auth/login/twitter",
            "statusCode": 404
        }
    ],
    "responseOverrides": {
        "404": {
            "rewrite": "/404",
            "statusCode": 404
        }
    },
    "globalHeaders": {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "content-security-policy": "default-src https: 'unsafe-inline' 'unsafe-eval'; img-src https: data:; frame-ancestors 'none';"
    },
    "mimeTypes": {
        ".json": "application/json"
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/staticwebapp.config.json
git commit -m "Fix: X-Frame-Options, security headers e bloqueio de auth providers no SWA"
```

---

## Task 6: Security headers no backend

**Files:**
- Modificar: `src/api_helpers.py:38-43`
- Modificar: `tests/test_api_helpers.py`

- [ ] **Step 1: Adicionar teste de security headers**

Em `tests/test_api_helpers.py`, adicionar classe:

```python
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
```

- [ ] **Step 2: Rodar — confirmar que falham**

```bash
python3 -m pytest tests/test_api_helpers.py::TestSecurityHeaders -v
# Esperado: FAIL — KeyError: 'X-Content-Type-Options'
```

- [ ] **Step 3: Adicionar headers em _cors_headers**

Em `src/api_helpers.py`, substituir `_cors_headers` (linhas 38-43):

De:
```python
def _cors_headers(request=None) -> dict:
    """Build CORS response headers with dynamic origin."""
    return {
        "Access-Control-Allow-Origin": _resolve_origin(request),
        "Access-Control-Allow-Credentials": "true",
    }
```

Para:
```python
def _cors_headers(request=None) -> dict:
    """Build CORS + security response headers with dynamic origin."""
    return {
        "Access-Control-Allow-Origin": _resolve_origin(request),
        "Access-Control-Allow-Credentials": "true",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
```

- [ ] **Step 4: Rodar testes**

```bash
python3 -m pytest tests/test_api_helpers.py -v
# Esperado: todos passam
```

- [ ] **Step 5: Commit**

```bash
git add src/api_helpers.py tests/test_api_helpers.py
git commit -m "Fix: security headers (X-Frame-Options, nosniff, Referrer-Policy) em todas as respostas"
```

---

## Task 7: Mensagens JWT genéricas

**Files:**
- Modificar: `src/auth.py:156-177`
- Modificar: `tests/test_auth.py`

- [ ] **Step 1: Adicionar teste para mensagem genérica (RED)**

Em `tests/test_auth.py`, adicionar na classe `TestRequireAuth`:

```python
    def test_invalid_token_returns_generic_message(self, monkeypatch):
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        monkeypatch.setenv("AZURE_AD_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_AD_CLIENT_ID", "test-client")
        from src.auth import _extract_and_validate

        req = _MockHttpRequest(headers={"Authorization": "Bearer invalid.token.here"})
        with pytest.raises(AuthenticationError, match="Authentication required"):
            _extract_and_validate(req)
```

- [ ] **Step 2: Rodar — confirmar que falha**

```bash
python3 -m pytest tests/test_auth.py::TestRequireAuth::test_invalid_token_returns_generic_message -v
# Esperado: FAIL — mensagem atual é "Invalid token format", não "Authentication required"
```

- [ ] **Step 3: Unificar mensagens de erro JWT (GREEN)**

Em `src/auth.py`, substituir `_extract_and_validate` (linhas 156-177):

```python
def _extract_and_validate(req) -> dict:
    """Extract and validate JWT from request. Returns user info dict."""
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthenticationError()  # default: "Authentication required"

    token = auth_header[7:]
    try:
        claims = _validate_jwt_token(token)
    except AuthenticationError as e:
        # Log the specific reason for debugging, return generic message to client
        logger.warning(f"JWT validation failed: {e}")
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
```

**Nota:** `_validate_jwt_token` continua com mensagens detalhadas internamente (para logging), mas `_extract_and_validate` captura e re-levanta com mensagem genérica. `_validate_group_claim` (ForbiddenError) NÃO é mascarada — é um 403, não 401.

- [ ] **Step 4: Fortalecer teste existente de missing auth header**

Em `tests/test_auth.py`, atualizar `test_missing_auth_header`:

```python
    def test_missing_auth_header(self, monkeypatch):
        monkeypatch.delenv("SKIP_AUTH", raising=False)
        from src.auth import require_auth

        @require_auth
        def endpoint(req):
            return _MockHttpResponse(200)

        req = _MockHttpRequest()
        with pytest.raises(AuthenticationError, match="Authentication required"):
            endpoint(req)
```

- [ ] **Step 5: Verificar compatibilidade com test_auth_integration.py**

```bash
python3 -m pytest tests/test_auth_integration.py -v
# Esperado: todos passam (testes usam pytest.raises(AuthenticationError) sem match específico)
```

- [ ] **Step 6: Rodar testes de auth completos**

```bash
python3 -m pytest tests/test_auth.py tests/test_auth_integration.py -v
# Esperado: 19 + 7 = 26 passed
```

- [ ] **Step 7: Commit**

```bash
git add src/auth.py tests/test_auth.py
git commit -m "Fix: mensagens JWT genéricas — sem information disclosure sobre tipo de falha"
```

---

## Task 8: Deploy e verificação final

**IMPORTANTE:** Solicitar aprovação do usuário antes de executar deploy e push.

- [ ] **Step 1: Rodar suíte completa**

```bash
python3 -m pytest tests/ -v --tb=short
# Esperado: todos os testes passam (base + ~18 novos)
```

- [ ] **Step 2: Deploy backend (com aprovação do usuário)**

```bash
func azure functionapp publish az-pg-spend-analysis-ai-agent --python
```

- [ ] **Step 3: Push para main (com aprovação do usuário, deploy frontend automático)**

```bash
git push origin main
```

- [ ] **Step 4: Verificar health público**

```bash
curl -s "https://az-pg-spend-analysis-ai-agent.azurewebsites.net/api/health" | python3 -m json.tool
# Esperado: {"status": "healthy", "version": "3.0"} (sem checks detalhados)
```

- [ ] **Step 5: Verificar HTTPS Only**

```bash
curl -s -o /dev/null -w "%{http_code}" "http://az-pg-spend-analysis-ai-agent.azurewebsites.net/api/health"
# Esperado: 301
```

- [ ] **Step 6: Verificar headers de segurança no frontend**

```bash
curl -s -D- "https://salmon-beach-05662180f.6.azurestaticapps.net/" 2>/dev/null | grep -iE "x-frame|x-content|referrer"
# Esperado: X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy: strict-origin-when-cross-origin
```

- [ ] **Step 7: Verificar GitHub auth bloqueado**

```bash
curl -s -o /dev/null -w "%{http_code}" "https://salmon-beach-05662180f.6.azurestaticapps.net/.auth/login/github"
# Esperado: 404
```
