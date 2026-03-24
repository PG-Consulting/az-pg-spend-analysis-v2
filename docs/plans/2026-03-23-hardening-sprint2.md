# Hardening Sprint 2 — Circuit Breaker, Rate Limit, ML Deprecation, CSP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 4 melhorias de robustez sem custo: circuit breaker no Grok, rate limiting por IP, deprecar ML legado (dead code), endurecimento CSP.

**Architecture:** Mudanças defensivas e aditivas. Nenhuma altera comportamento funcional existente. Circuit breaker e rate limiter são módulos independentes adicionados como decorators/wrappers.

**Tech Stack:** Python 3.12, Next.js 14 (static export), Azure Static Web Apps

---

## Mapa de Arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `src/llm_classifier.py` | Modificar | Circuit breaker no Grok API |
| `src/api_helpers.py` | Modificar | Rate limiter per-IP como decorator |
| `blueprints/classification_bp.py` | Modificar | Aplicar rate_limit no SubmitTaxonomyJob |
| `frontend/src/components/taxonomy/TrainTab.tsx` | **Deletar** | Componente não importado (dead code) |
| `frontend/src/components/taxonomy/ModelsTab.tsx` | **Deletar** | Componente não importado (dead code) |
| `frontend/staticwebapp.config.json` | Modificar | CSP endurecido |
| `tests/test_llm_circuit_breaker.py` | **Criar** | Testes do circuit breaker |
| `tests/test_rate_limit.py` | **Criar** | Testes do rate limiter |

---

## Task 1: Circuit Breaker no Grok API

**Files:**
- Modificar: `src/llm_classifier.py` (adicionar CircuitBreaker class + integrar em _call_openai_api_inner)
- Criar: `tests/test_llm_circuit_breaker.py`

**Design:** Circuit breaker com 3 estados (CLOSED → OPEN → HALF_OPEN). Após `failure_threshold` falhas consecutivas, abre o circuito por `recovery_timeout` segundos. Durante OPEN, retorna fallback imediato sem chamar a API. Após timeout, permite 1 request de teste (HALF_OPEN).

- [ ] **Step 1: Escrever testes**

Criar `tests/test_llm_circuit_breaker.py`:

```python
"""Tests for circuit breaker in llm_classifier."""

import time
from unittest.mock import patch

from src.llm_classifier import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt() is True

    def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt() is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_attempt() is False

    def test_success_resets_count(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(1.1)
        assert cb.can_attempt() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(1.1)
        cb.can_attempt()  # transitions to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(1.1)
        cb.can_attempt()  # transitions to HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
```

- [ ] **Step 2: Rodar testes — confirmar que falham**

```bash
python3 -m pytest tests/test_llm_circuit_breaker.py -v
# Esperado: ImportError (CircuitBreaker, CircuitState não existem)
```

- [ ] **Step 3: Implementar CircuitBreaker**

Em `src/llm_classifier.py`, adicionar após as constantes existentes (depois de `_LLM_SEMAPHORE`):

```python
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Simple circuit breaker for external API calls.

    CLOSED: normal operation, requests pass through.
    OPEN: fail fast, no requests sent (after failure_threshold consecutive failures).
    HALF_OPEN: one test request allowed (after recovery_timeout seconds).
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitState.CLOSED

    def can_attempt(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN: allow one test request

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN


# Circuit breaker instance (5 consecutive failures → open for 60s)
_CIRCUIT_BREAKER = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
```

- [ ] **Step 4: Integrar na `_call_openai_api_inner`**

No início de `_call_openai_api_inner()`, antes do loop de retry, adicionar check do circuit breaker. Se OPEN, retornar fallback imediato. No final do loop: record_success em caso de sucesso, record_failure em caso de falha.

Adicionar no início da função (dentro, antes do `for attempt`):
```python
if not _CIRCUIT_BREAKER.can_attempt():
    logger.warning("Circuit breaker OPEN — skipping Grok API call, returning fallback")
    return [
        {
            "description": item.get("description", ""),
            "N1": "Não Identificado", "N2": "Não Identificado",
            "N3": "Não Identificado", "N4": "Não Identificado",
            "source": "LLM (Batch)", "confidence": 0.0,
        }
        for item in items
    ], None
```

Após resposta bem-sucedida (onde `response.status_code == 200`), adicionar:
```python
_CIRCUIT_BREAKER.record_success()
```

No fallback final (quando todos os retries falharam), adicionar antes do return:
```python
_CIRCUIT_BREAKER.record_failure()
```

- [ ] **Step 5: Rodar testes**

```bash
python3 -m pytest tests/test_llm_circuit_breaker.py -v
# Esperado: 7 passed
python3 -m pytest tests/ -v --tb=short
# Esperado: todos passam
```

- [ ] **Step 6: Commit**

```bash
git add src/llm_classifier.py tests/test_llm_circuit_breaker.py
git commit -m "Adicionando circuit breaker no Grok API — fail fast após 5 falhas consecutivas"
```

---

## Task 2: Rate Limiting por IP

**Files:**
- Modificar: `src/api_helpers.py` (adicionar rate_limit decorator)
- Modificar: `blueprints/classification_bp.py` (aplicar no SubmitTaxonomyJob)
- Criar: `tests/test_rate_limit.py`

**Design:** Sliding window per-IP. Decorator `@rate_limit(requests=N, window=M)`. In-memory, thread-safe. Retorna 429 com Retry-After header.

**Onde aplicar:** Apenas no SubmitTaxonomyJob (endpoint que dispara chamadas LLM caras). Os demais endpoints são leves e não justificam throttle.

- [ ] **Step 1: Escrever testes**

Criar `tests/test_rate_limit.py`:

```python
"""Tests for rate limiting decorator in api_helpers."""

import time
import json
from unittest.mock import MagicMock

from src.api_helpers import rate_limit, _rate_limit_buckets


class _MockRequest:
    def __init__(self, ip="1.2.3.4"):
        self.headers = {"X-Forwarded-For": ip}


class _MockResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.headers = {}


class TestRateLimit:
    def setup_method(self):
        _rate_limit_buckets.clear()

    def test_allows_requests_under_limit(self):
        @rate_limit(requests=5, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest()
        for _ in range(5):
            resp = endpoint(req)
            assert resp.status_code == 200

    def test_blocks_requests_over_limit(self):
        @rate_limit(requests=3, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest()
        for _ in range(3):
            endpoint(req)
        resp = endpoint(req)
        assert resp.status_code == 429

    def test_returns_retry_after_header(self):
        @rate_limit(requests=1, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest()
        endpoint(req)
        resp = endpoint(req)
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_different_ips_tracked_separately(self):
        @rate_limit(requests=2, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req_a = _MockRequest(ip="1.1.1.1")
        req_b = _MockRequest(ip="2.2.2.2")
        endpoint(req_a)
        endpoint(req_a)
        resp_a = endpoint(req_a)
        resp_b = endpoint(req_b)
        assert resp_a.status_code == 429
        assert resp_b.status_code == 200

    def test_window_expires(self):
        @rate_limit(requests=1, window=1)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest()
        endpoint(req)
        resp = endpoint(req)
        assert resp.status_code == 429
        time.sleep(1.1)
        resp = endpoint(req)
        assert resp.status_code == 200

    def test_bypasses_options(self):
        @rate_limit(requests=1, window=60)
        def endpoint(req):
            return _MockResponse(200)

        req = _MockRequest()
        req.method = "OPTIONS"
        resp = endpoint(req)
        assert resp.status_code == 200
```

- [ ] **Step 2: Rodar testes — confirmar que falham**

```bash
python3 -m pytest tests/test_rate_limit.py -v
# Esperado: ImportError
```

- [ ] **Step 3: Implementar rate_limit**

Em `src/api_helpers.py`, adicionar após `import functools`:

```python
import threading
import time as _time
from collections import defaultdict
```

E após a função `handle_errors`, adicionar:

```python
# --- Rate limiting ---

_rate_limit_buckets: dict[str, list[float]] = defaultdict(list)
_rate_limit_lock = threading.Lock()


def _get_client_ip(request) -> str:
    """Extract client IP from request (handles Azure proxy headers)."""
    if request is None:
        return "unknown"
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.headers.get("X-Client-IP", "unknown")


def rate_limit(requests: int = 100, window: int = 60):
    """Decorator: per-IP sliding window rate limiter.

    Returns 429 with Retry-After header when limit is exceeded.
    Bypasses OPTIONS preflight requests.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            req = args[0] if args and hasattr(args[0], "headers") else None

            # Bypass OPTIONS
            if req and hasattr(req, "method") and req.method == "OPTIONS":
                return fn(*args, **kwargs)

            client_ip = _get_client_ip(req)
            now = _time.time()

            with _rate_limit_lock:
                bucket = _rate_limit_buckets[client_ip]
                bucket[:] = [ts for ts in bucket if now - ts < window]

                if len(bucket) >= requests:
                    reset_time = bucket[0] + window
                    return func.HttpResponse(
                        body=json.dumps(
                            {"error": "Rate limit exceeded. Try again later."},
                            ensure_ascii=False,
                        ),
                        status_code=429,
                        mimetype="application/json",
                        headers={
                            **_cors_headers(req),
                            "Retry-After": str(int(reset_time - now) + 1),
                        },
                    )

                bucket.append(now)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
```

- [ ] **Step 4: Aplicar no SubmitTaxonomyJob**

Em `blueprints/classification_bp.py`, adicionar import:
```python
from src.api_helpers import rate_limit
```

No endpoint `SubmitTaxonomyJob`, adicionar `@rate_limit(requests=10, window=60)` entre `@handle_errors` e `@require_auth`:
```python
@classification_bp.route(route="SubmitTaxonomyJob", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("SubmitTaxonomyJob")
@rate_limit(requests=10, window=60)
@require_auth
def SubmitTaxonomyJob(req: func.HttpRequest) -> func.HttpResponse:
```

(10 jobs por minuto por IP — generoso para uso normal, bloqueia loops acidentais)

- [ ] **Step 5: Rodar testes**

```bash
python3 -m pytest tests/test_rate_limit.py -v
# Esperado: 6 passed
python3 -m pytest tests/ -v --tb=short
# Esperado: todos passam
```

- [ ] **Step 6: Commit**

```bash
git add src/api_helpers.py blueprints/classification_bp.py tests/test_rate_limit.py
git commit -m "Adicionando rate limiting por IP no SubmitTaxonomyJob — 10 req/min"
```

---

## Task 3: Deprecar ML Legado (dead code)

**Files:**
- Deletar: `frontend/src/components/taxonomy/TrainTab.tsx` (zero imports)
- Deletar: `frontend/src/components/taxonomy/ModelsTab.tsx` (zero imports)

**NOTA:** Os backend endpoints (`TrainModel`, `SetActiveModel`, etc.) e os módulos Python (`ml_classifier.py`, `hybrid_classifier.py`, `model_trainer.py`) são mantidos por enquanto — os setores `varejo` e `educacional` ainda podem usá-los via `use_legacy_ml=True`. A deprecação é apenas do frontend morto.

- [ ] **Step 1: Verificar que os componentes não são importados**

```bash
cd frontend && grep -r "TrainTab\|ModelsTab" src/ --include="*.tsx" --include="*.ts" | grep -v "TrainTab.tsx\|ModelsTab.tsx"
# Esperado: nenhum resultado (zero imports)
```

- [ ] **Step 2: Deletar componentes mortos**

```bash
rm frontend/src/components/taxonomy/TrainTab.tsx
rm frontend/src/components/taxonomy/ModelsTab.tsx
```

- [ ] **Step 3: Build do frontend**

```bash
cd frontend && npm run build
# Esperado: build sem erros (componentes não eram importados)
```

- [ ] **Step 4: Commit**

```bash
git add -u frontend/src/components/taxonomy/
git commit -m "Refactor: removendo TrainTab e ModelsTab — componentes não utilizados (ML legado)"
```

---

## Task 4: CSP Endurecido

**Files:**
- Modificar: `frontend/staticwebapp.config.json`

**LIMITAÇÃO:** Next.js com `output: 'export'` gera HTML com inline scripts para hydration. Azure Static Web Apps não suporta nonces server-side. Portanto, `unsafe-inline` para scripts é necessário. Podemos:
- Remover `unsafe-eval` (Next.js produção não precisa de eval)
- Adicionar `script-src`, `style-src`, `connect-src` explícitos
- Adicionar `base-uri 'self'`

- [ ] **Step 1: Atualizar CSP**

Em `frontend/staticwebapp.config.json`, substituir a linha `content-security-policy`:

De:
```
"content-security-policy": "default-src https: 'unsafe-inline' 'unsafe-eval'; img-src https: data:; frame-ancestors 'none';"
```

Para:
```
"content-security-policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; font-src 'self'; connect-src 'self' https://*.azurewebsites.net https://login.microsoftonline.com https://*.microsoftonline.com; frame-ancestors 'none'; base-uri 'self';"
```

**Mudanças:**
- `default-src`: de `https: 'unsafe-inline' 'unsafe-eval'` para `'self'` (mais restritivo)
- `script-src`: `'self' 'unsafe-inline'` (sem `unsafe-eval` — Next.js prod não precisa)
- `style-src`: `'self' 'unsafe-inline'` (necessário para Tailwind/styled components)
- `connect-src`: whitelist explícita (API backend + Azure AD login)
- `font-src`: `'self'` (fonts locais)
- `base-uri`: `'self'` (previne base tag injection)
- **Removido**: `unsafe-eval` (melhoria significativa contra XSS)

- [ ] **Step 2: Build e verificar**

```bash
cd frontend && npm run build
# Esperado: build sem erros
```

- [ ] **Step 3: Commit**

```bash
git add frontend/staticwebapp.config.json
git commit -m "Fix: CSP endurecido — removido unsafe-eval, connect-src restrito, base-uri adicionado"
```

---

## Task 5: Deploy e verificação

**IMPORTANTE:** Solicitar aprovação do usuário antes de executar.

- [ ] **Step 1: Rodar suíte completa**

```bash
python3 -m pytest tests/ -v --tb=short
# Esperado: todos passam
```

- [ ] **Step 2: Deploy backend**

```bash
func azure functionapp publish az-pg-spend-analysis-ai-agent --python
```

- [ ] **Step 3: Push para main**

```bash
git push origin main
```

- [ ] **Step 4: Verificar CSP no frontend**

```bash
curl -s -D- "https://salmon-beach-05662180f.6.azurestaticapps.net/" 2>/dev/null | grep -i "content-security-policy"
# Esperado: CSP sem unsafe-eval, com connect-src restrito
```

- [ ] **Step 5: Verificar que o app funciona**

Acessar https://salmon-beach-05662180f.6.azurestaticapps.net e verificar:
- Login funciona
- Nenhum erro no console do navegador (violações CSP)
- API health responde
