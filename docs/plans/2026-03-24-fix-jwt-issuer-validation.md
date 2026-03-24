# Fix JWT Issuer Validation — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir erro 401 em produção causado por mismatch de issuer entre tokens Azure AD v1.0 e validação hardcoded v2.0 no backend, garantindo que todos os endpoints funcionem para qualquer usuário autenticado.

**Arquitetura:** O `_validate_jwt_token()` em `src/auth.py` valida o issuer como `https://login.microsoftonline.com/{tenant}/v2.0`, mas tokens Azure AD com `accessTokenAcceptedVersion: null` (default) usam issuer v1.0 (`https://sts.windows.net/{tenant}/`). A correção aceita ambos os formatos. PyJWT >= 2.4 suporta lista de issuers nativamente.

**Tech Stack:** Python 3.9+, PyJWT >= 2.8, pytest, Azure AD / MSAL

---

## Diagnóstico

### Causa Raiz

O app registration no Azure AD provavelmente tem `accessTokenAcceptedVersion: null` (default). Isso gera tokens v1.0 com:
- `iss` = `https://sts.windows.net/{tenantId}/` (formato v1.0)
- `aud` = `api://{clientId}` (igual ao v2.0)

O backend valida com issuer v2.0 hardcoded (`https://login.microsoftonline.com/{tenant}/v2.0`), causando `InvalidIssuerError` → 401 para **TODOS** os endpoints.

### Por Que Parece Funcionar

| Endpoint | Tipo | Comportamento no 401 |
|----------|------|---------------------|
| `GetUserProfile` | GET | `catch` silencioso → `user = null` (AuthContext:253) |
| `ListSectors` | GET | `catch` → fallback cache vazio (useProjects:29-33) |
| `ListProjects` | GET | `catch` → fallback cache vazio (useProjects:29-33) |
| `CreateProject` | POST | `catch` → **mostra erro** ao usuário (CreateProjectModal:108) |

### Confirmação via Logs

Nos logs do Azure Functions deve haver: `JWT validation failed: Invalid token issuer`

---

## Arquivos Afetados

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `src/auth.py` | Modificar | Aceitar issuers v1.0 e v2.0 |
| `tests/test_auth.py` | Modificar | Testes para ambos formatos de issuer |
| `frontend/src/contexts/AuthContext.tsx` | Modificar | Surfacear erros de auth (não silenciar 401) |
| `frontend/src/__tests__/auth-context.test.tsx` | Criar (se necessário) | Testar tratamento de erro no AuthContext |

---

## Task 1: Testes para validação de issuer v1.0 e v2.0

**Files:**
- Modify: `tests/test_auth.py`

- [ ] **Step 1: Adicionar testes para validação real de issuer v1.0 e v2.0**

```python
@pytest.mark.real_auth
class TestValidateJwtTokenIssuers:
    """Testa que _validate_jwt_token aceita ambos formatos de issuer."""

    @patch("src.auth._get_jwks_keys")
    @patch("jwt.get_unverified_header")
    def test_v1_issuer_accepted(self, mock_header, mock_jwks, monkeypatch):
        """Token com issuer v1.0 (sts.windows.net) deve ser aceito."""
        monkeypatch.setenv("AZURE_AD_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_AD_CLIENT_ID", "test-client")

        mock_header.return_value = {"kid": "key-1", "alg": "RS256"}

        # Mock JWKS key
        from unittest.mock import ANY
        import jwt as pyjwt

        # Gerar par de chaves RSA para teste
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        # Criar JWK a partir da chave pública
        public_numbers = public_key.public_numbers()
        import base64

        def _int_to_base64(n, length=None):
            b = n.to_bytes((n.bit_length() + 7) // 8, byteorder="big")
            return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

        jwk = {
            "kid": "key-1",
            "kty": "RSA",
            "n": _int_to_base64(public_numbers.n),
            "e": _int_to_base64(public_numbers.e),
        }
        mock_jwks.return_value = [jwk]

        # Criar token com issuer v1.0
        token = pyjwt.encode(
            {
                "iss": "https://sts.windows.net/test-tenant/",
                "aud": "api://test-client",
                "preferred_username": "user@test.com",
                "name": "Test User",
                "exp": 9999999999,
                "iat": 1000000000,
                "nbf": 1000000000,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "key-1"},
        )

        from src.auth import _validate_jwt_token

        claims = _validate_jwt_token(token)
        assert claims["preferred_username"] == "user@test.com"

    @patch("src.auth._get_jwks_keys")
    @patch("jwt.get_unverified_header")
    def test_v2_issuer_accepted(self, mock_header, mock_jwks, monkeypatch):
        """Token com issuer v2.0 (login.microsoftonline.com) deve ser aceito."""
        monkeypatch.setenv("AZURE_AD_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_AD_CLIENT_ID", "test-client")

        mock_header.return_value = {"kid": "key-1", "alg": "RS256"}

        from cryptography.hazmat.primitives.asymmetric import rsa
        import jwt as pyjwt
        import base64

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        public_numbers = public_key.public_numbers()

        def _int_to_base64(n, length=None):
            b = n.to_bytes((n.bit_length() + 7) // 8, byteorder="big")
            return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

        jwk = {
            "kid": "key-1",
            "kty": "RSA",
            "n": _int_to_base64(public_numbers.n),
            "e": _int_to_base64(public_numbers.e),
        }
        mock_jwks.return_value = [jwk]

        token = pyjwt.encode(
            {
                "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
                "aud": "api://test-client",
                "preferred_username": "user@test.com",
                "name": "Test User",
                "exp": 9999999999,
                "iat": 1000000000,
                "nbf": 1000000000,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "key-1"},
        )

        from src.auth import _validate_jwt_token

        claims = _validate_jwt_token(token)
        assert claims["preferred_username"] == "user@test.com"

    @patch("src.auth._get_jwks_keys")
    @patch("jwt.get_unverified_header")
    def test_unknown_issuer_rejected(self, mock_header, mock_jwks, monkeypatch):
        """Token com issuer desconhecido deve ser rejeitado."""
        monkeypatch.setenv("AZURE_AD_TENANT_ID", "test-tenant")
        monkeypatch.setenv("AZURE_AD_CLIENT_ID", "test-client")

        mock_header.return_value = {"kid": "key-1", "alg": "RS256"}

        from cryptography.hazmat.primitives.asymmetric import rsa
        import jwt as pyjwt
        import base64

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        public_numbers = public_key.public_numbers()

        def _int_to_base64(n, length=None):
            b = n.to_bytes((n.bit_length() + 7) // 8, byteorder="big")
            return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

        jwk = {
            "kid": "key-1",
            "kty": "RSA",
            "n": _int_to_base64(public_numbers.n),
            "e": _int_to_base64(public_numbers.e),
        }
        mock_jwks.return_value = [jwk]

        token = pyjwt.encode(
            {
                "iss": "https://evil.example.com/",
                "aud": "api://test-client",
                "preferred_username": "user@test.com",
                "name": "Test User",
                "exp": 9999999999,
                "iat": 1000000000,
                "nbf": 1000000000,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "key-1"},
        )

        from src.auth import _validate_jwt_token
        from src.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError, match="Invalid token issuer"):
            _validate_jwt_token(token)
```

- [ ] **Step 2: Rodar testes e verificar que `test_v1_issuer_accepted` FALHA**

Run: `python3 -m pytest tests/test_auth.py::TestValidateJwtTokenIssuers::test_v1_issuer_accepted -v`
Expected: FAIL com `AuthenticationError: Invalid token issuer`

- [ ] **Step 3: Commit dos testes**

```bash
git add tests/test_auth.py
git commit -m "Adicionando testes para validação de issuer v1.0 e v2.0"
```

---

## Task 2: Fix — aceitar issuers v1.0 e v2.0 no backend

**Files:**
- Modify: `src/auth.py:88-104`

- [ ] **Step 1: Atualizar `_validate_jwt_token` para aceitar ambos issuers**

Substituir linhas 93-114 em `src/auth.py` (do `issuer = ...` até o último `except`).
O bloco completo após a substituição fica:

```python
    # Accept both v2.0 and v1.0 issuer formats.
    # v1.0 tokens use sts.windows.net when accessTokenAcceptedVersion is null (default).
    # v2.0 JWKS endpoint serves the same signing keys as v1.0, so a single
    # JWKS URL is sufficient for both token versions.
    issuers = [
        f"https://login.microsoftonline.com/{tenant_id}/v2.0",  # v2.0
        f"https://sts.windows.net/{tenant_id}/",                 # v1.0
    ]
    # Access tokens for custom API scopes (api://{clientId}/...) have
    # audience = "api://{clientId}", not the bare clientId.
    audience = f"api://{client_id}"

    try:
        claims = jwt.decode(
            token,
            key=rsa_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuers,
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
```

> **Nota:** PyJWT >= 2.4 aceita lista no parâmetro `issuer` — quando recebe uma lista, verifica se `iss` do token está na lista. Nossa versão é >= 2.8 (requirements.txt). Os `except` blocks permanecem iguais aos originais.

- [ ] **Step 2: Rodar testes de issuer e verificar que TODOS passam**

Run: `python3 -m pytest tests/test_auth.py::TestValidateJwtTokenIssuers -v`
Expected: 3/3 PASS

- [ ] **Step 3: Rodar suite completa de testes de auth**

Run: `python3 -m pytest tests/test_auth.py tests/test_auth_integration.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit do fix**

```bash
git add src/auth.py
git commit -m "Fix: aceitar issuer v1.0 e v2.0 nos tokens Azure AD"
```

---

## Task 3: Melhorar logging de auth para debugging

**Files:**
- Modify: `src/auth.py:164-169`

- [ ] **Step 1: Adicionar log mais detalhado no `_extract_and_validate`**

Substituir o bloco de catch em `_extract_and_validate` (linhas 164-169):

```python
    try:
        claims = _validate_jwt_token(token)
    except AuthenticationError as e:
        # Log específico para facilitar debugging em produção
        logger.warning(
            "JWT validation failed for %s: %s",
            req.headers.get("X-Forwarded-For", "unknown-ip"),
            e,
        )
        raise AuthenticationError()  # generic message to client
```

- [ ] **Step 2: Rodar testes**

Run: `python3 -m pytest tests/test_auth.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/auth.py
git commit -m "Ajuste: logging mais detalhado em falhas de autenticação JWT"
```

---

## Task 4: Frontend — surfacear erros de auth em vez de silenciar

**Files:**
- Modify: `frontend/src/contexts/AuthContext.tsx:239-257`

- [ ] **Step 1: Modificar `fetchProfile` para tratar 401 como erro visível**

O `AuthContext` silencia erros do `GetUserProfile` — o usuário vê a tela mas sem perfil. Ajustar para:
- Se `getAccessToken()` retorna `null`: retry silencioso (pode ser transitório — popup bloqueado, cache MSAL, etc.)
- Se backend retorna 401: `logoutRedirect()` (token inválido confirmado pelo servidor)
- Outros erros (rede, 500): mostrar no console, não forçar logout

> **IMPORTANTE:** NÃO chamar `logoutRedirect()` quando `getAccessToken()` retorna `null` — isso causa loop infinito porque MSAL pode falhar por razões transitórias (aba inativa, popup bloqueado, cache race). Só redirecionar para login quando o BACKEND confirmar 401.

```typescript
    const fetchProfile = async () => {
      try {
        const token = await getAccessToken();
        if (!token) {
          // Token null = MSAL não conseguiu adquirir (transitório).
          // NÃO fazer logoutRedirect() aqui — causaria loop infinito.
          console.warn('[Auth] No access token available — will retry on next interaction');
          setIsLoading(false);
          return;
        }
        const profile = await apiClient.getUserProfile(token);
        setUser({
          email: profile.email,
          name: profile.name,
          role: profile.role as 'admin' | 'consultor',
        });
        profileFetchedRef.current = true;
      } catch (err: any) {
        const status = err?.response?.status;
        if (status === 401) {
          // Backend CONFIRMOU que o token é inválido — seguro fazer logout
          console.warn('[Auth] Token rejected by backend (401) — forcing re-login');
          instance.logoutRedirect();
          return;
        }
        // Outros erros (rede, 500, CORS) — não forçar logout
        console.error('[Auth] Failed to fetch user profile:', err);
      } finally {
        setIsLoading(false);
      }
    };
```

- [ ] **Step 2: Rodar build do frontend para verificar TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: sem erros

- [ ] **Step 3: Commit**

```bash
git add frontend/src/contexts/AuthContext.tsx
git commit -m "Fix: surfacear erros de auth no frontend em vez de silenciar 401"
```

---

## Task 5: Rodar suite completa de testes e verificar

- [ ] **Step 1: Backend — suite completa**

Run: `python3 -m pytest tests/ -v --tb=short`
Expected: 406+ testes passando (originais + novos de issuer)

- [ ] **Step 2: Frontend — suite completa**

Run: `cd frontend && npx jest --verbose`
Expected: 50 testes passando

- [ ] **Step 3: Commit final e deploy**

```bash
# Deploy backend (manual)
func azure functionapp publish az-pg-spend-analysis-ai-agent --python
```

> **Nota:** Deploy precisa de aprovação explícita do usuário antes de executar.

---

## Verificação Pós-Deploy

1. Acessar a aplicação com o usuário de teste
2. Verificar que `GetUserProfile` retorna perfil (nome + role no header)
3. Verificar que `ListSectors` e `ListProjects` retornam dados (ou vazio real, não erro)
4. Criar um projeto com setor existente → deve funcionar sem 401
5. Verificar logs do Azure Functions — sem mensagens de "JWT validation failed"

## Nota sobre CreateSector

O endpoint `CreateSector` usa `@require_admin`. Se o usuário não estiver em `ADMIN_EMAILS`, receberá 403 (não 401). Isso é **comportamento correto** — criar setores é ação de admin. Consultores devem usar setores existentes ou pedir a um admin para criar.

Se desejado no futuro: permitir que consultores criem setores mudando `@require_admin` para `@require_auth` em `blueprints/projects_bp.py:47`.
