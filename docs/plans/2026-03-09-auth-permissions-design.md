# Design: Autenticação Entra ID + Permissões (Admin/Consultor)

**Data:** 2026-03-09
**Status:** Aprovado (revisão 3 — 5+2 CRITICALs resolvidos)

## Contexto

A plataforma Spend Analysis v3 opera sem qualquer autenticação — todos os endpoints usam `AuthLevel.ANONYMOUS`, não há login no frontend, e operações críticas (promover KB do setor, deletar setores) são acessíveis por qualquer pessoa. A PG Consultoria já usa Azure AD (Entra ID) para contas corporativas.

## Decisões

| Decisão | Escolha | Alternativas descartadas |
|---------|---------|--------------------------|
| Provider de identidade | Azure AD (Entra ID) — tenant corporativo existente | Auth0, Firebase Auth, Supabase Auth |
| Roles | 2 roles: Consultor e Admin | 3 roles com Viewer (desnecessário) |
| Definição de admins | Variável de ambiente `ADMIN_EMAILS` | Grupo Entra ID (futuro), tabela no app |
| Proteção do app | Login obrigatório para tudo | Leitura livre / escrita protegida |
| Fluxo de login | MSAL.js no frontend + validação JWT no backend | Easy Auth (Azure built-in) |

## Arquitetura

```
Usuário → Next.js (MSAL.js login) → Entra ID → JWT access token
                                                      ↓
Next.js → API request + Bearer token → Azure Functions
                                            ↓
                                   Middleware valida JWT
                                   Extrai email do token
                                   Checa ADMIN_EMAILS → role
                                            ↓
                                   Endpoint executa (ou 403)
```

## Frontend (MSAL.js)

### Dependências

- `@azure/msal-browser@^3.x`
- `@azure/msal-react@^2.x`

### Componentes

- **`MsalProvider`** — wrapping `_app.tsx`, todas as páginas protegidas
- **`AuthGuard`** — componente que redireciona para login se não autenticado; exibe loading/splash enquanto MSAL inicializa
- **`AuthContext`** — expõe `user`, `role` (admin/consultor), `accessToken`, `logout()`
- **`useAuth` hook** — acesso ao contexto de auth

### Fluxo

1. App carrega → `MsalProvider` inicializa → exibe splash/loading enquanto verifica sessão
2. `AuthGuard` verifica se há sessão ativa
3. Se não autenticado → redirect para login Entra ID
4. Após login → MSAL processa redirect callback (limpa query params da URL)
5. Recebe token JWT via `acquireTokenSilent()` (usa refresh token para renovação automática)
6. Chama `GET /api/GetUserProfile` com Bearer token → recebe `{email, name, role}`
7. Armazena role no `AuthContext`
8. Todas as requests subsequentes incluem `Authorization: Bearer <token>`

### Token Refresh

- `acquireTokenSilent()` é chamado antes de cada request via interceptor Axios
- Se o token expirou (60-90 min), MSAL usa o refresh token para obter um novo silenciosamente
- Se o refresh token também expirou → redirect para login interativo

### Migração do `api.ts`

- `getAuthHeaders()` atual retorna `{'x-functions-key': FUNCTION_KEY}` — será substituído por `{'Authorization': 'Bearer <token>'}` obtido do `AuthContext`
- `x-functions-key` será removido (auth é tratada na camada Python, não no host Azure Functions)

### UI Condicional

- Botões de "Promover para KB do setor", "Importar KB", "Editar/Deletar KB do setor" visíveis apenas para `role === "admin"`
- Criação/exclusão de setores visível apenas para admins
- Indicador visual do usuário logado + role no header

## Backend (Azure Functions)

### AuthLevel permanece ANONYMOUS

**IMPORTANTE:** Todos os endpoints DEVEM manter `AuthLevel.ANONYMOUS`. A autenticação é tratada na camada de aplicação (decorators Python), não pelo host Azure Functions. Não alterar para `AuthLevel.FUNCTION` ou `AuthLevel.ADMIN`.

### CORS — Correções obrigatórias

1. **`api_helpers.py` — `options_response()`**: Atualizar headers:
   ```
   "Access-Control-Allow-Headers": "Content-Type, Authorization"
   "Access-Control-Allow-Credentials": "true"
   "Access-Control-Max-Age": "3600"
   ```

2. **`api_helpers.py` — `json_response()` e `error_response()`**: Substituir `"Access-Control-Allow-Origin": "*"` por origin dinâmica — ecoar o header `Origin` da request (ou origin fixa de config). Wildcard `*` é incompatível com `Access-Control-Allow-Credentials: true`. Adicionar `"Access-Control-Allow-Credentials": "true"` nas respostas.

3. **`host.json`**: Atualizar configuração CORS:
   - `allowedOrigins`: substituir `["*"]` por origins específicas (`["http://localhost:3000", "https://<production-url>"]`)
   - `supportCredentials`: alterar para `true`

4. **Endpoints sem `OPTIONS`**: Todos os endpoints em `knowledge_bp.py`, `projects_bp.py` e `review_bp.py` que não registram o método `OPTIONS` devem ser atualizados para incluí-lo e retornar `options_response()` no guard de OPTIONS.

### Módulo de Auth (`src/auth.py`)

- **Biblioteca**: `PyJWT>=2.8.0` + `cryptography>=42.0.0` (para RS256)
- **Cache JWKS**: Buscar chaves públicas de `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys` e cachear em memória com TTL (ex: 24h). Revalidar se assinatura falhar (key rotation).
- Valida JWT: assinatura RS256, `aud` = `AZURE_AD_CLIENT_ID`, `iss` = tenant, `exp` não expirado
- Extrai email via claim `preferred_username` ou `email`
- Resolve role: email (`.strip().lower()`) em `ADMIN_EMAILS` (cada email `.strip().lower()`) → `"admin"`, senão → `"consultor"`
- Se `ADMIN_EMAILS` vazio ou não definido → todos são consultores

### Exceções de Auth (`src/exceptions.py`)

Novas exceções que herdam de `SpendAnalysisError`:
- `AuthenticationError` — HTTP 401 (token ausente, inválido ou expirado)
- `ForbiddenError` — HTTP 403 (role insuficiente)

### Decorators e Ordem de Stacking

**`@require_auth` faz bypass automático de OPTIONS.** O decorator detecta `req.method == "OPTIONS"` e delega direto para a função sem validar JWT. Isso é obrigatório porque o decorator executa ANTES do corpo da função — um guard de OPTIONS dentro da função nunca seria alcançado.

```python
# Implementação do decorator (em src/auth.py):
def require_auth(fn):
    @wraps(fn)
    def wrapper(req, *args, **kwargs):
        if req.method == "OPTIONS":       # Bypass: preflight CORS não tem token
            return fn(req, *args, **kwargs)
        # ... validação JWT, extração de email, resolução de role ...
        return fn(req, *args, **kwargs)
    return wrapper
```

**Uso nos endpoints:**

```python
@bp.route(route="Endpoint", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("Endpoint")        # 1. Captura TODAS as exceções (incl. auth)
@require_auth                      # 2. Bypass OPTIONS, valida JWT nos demais
def endpoint(req):
    if req.method == "OPTIONS":    # 3. Retorna preflight CORS
        return options_response(req)
    ...
```

**Ordem**: `@route` → `@handle_errors` → `@require_auth` → função

### `@require_admin` — Comportamento

`@require_admin` compõe com `@require_auth` internamente — NÃO empilhar ambos:

```python
def require_admin(fn):
    @wraps(fn)
    def wrapper(req, *args, **kwargs):
        if req.method == "OPTIONS":
            return fn(req, *args, **kwargs)
        # ... mesma validação JWT de require_auth ...
        # ... + verifica se email está em ADMIN_EMAILS ...
        # Se não admin → raise ForbiddenError("Acesso restrito a administradores")
        return fn(req, *args, **kwargs)
    return wrapper
```

**Uso:** `@handle_errors` → `@require_admin` (sem `@require_auth` adicional)

### Endpoints isentos de auth

- `GET /api/health` — health check, sem auth
- **Worker timer trigger (`worker_bp.py`)** — NÃO é endpoint HTTP, é `@timer_trigger`. Não recebe headers HTTP. **NÃO aplicar `@require_auth`**. O worker continua funcionando sem autenticação.
- Handlers de `OPTIONS` — preflight CORS, sem auth

### Endpoint novo

- `GET /api/GetUserProfile` — retorna `{email, name, role}` (protegido por `@require_auth`)

### Variáveis de ambiente novas

```bash
AZURE_AD_TENANT_ID=             # Tenant ID da PG no Entra ID
AZURE_AD_CLIENT_ID=             # Application (client) ID do app registration
ADMIN_EMAILS=                   # Lista separada por vírgula (ex: joao@pg.com,maria@pg.com)
```

### Dependências Python novas

```
PyJWT>=2.8.0
cryptography>=42.0.0
```

### Mapa de Permissões (completo)

| Endpoint | Auth | Role |
|----------|------|------|
| `GET /api/health` | Nenhuma | Livre |
| Worker timer trigger | N/A (não é HTTP) | N/A |
| `GET /api/GetUserProfile` | `@require_auth` | Consultor + Admin |
| `GET /api/ListSectors` | `@require_auth` | Consultor + Admin |
| `GET /api/ListProjects` | `@require_auth` | Consultor + Admin |
| `POST /api/CreateProject` | `@require_auth` | Consultor + Admin |
| `PUT /api/UpdateProject` | `@require_auth` | Consultor + Admin |
| `DELETE /api/DeleteProject` | `@require_auth` | Consultor + Admin |
| `GET /api/GetProjectHierarchy` | `@require_auth` | Consultor + Admin |
| `POST /api/CancelJob` | `@require_auth` | Consultor + Admin |
| `POST /api/SubmitClassificationJob` | `@require_auth` | Consultor + Admin |
| `GET /api/GetJobStatus` | `@require_auth` | Consultor + Admin |
| `GET /api/GetJobResults` | `@require_auth` | Consultor + Admin |
| `POST /api/ReclassifyItems` | `@require_auth` | Consultor + Admin |
| `POST /api/ApproveClassifications` | `@require_auth` | Consultor + Admin |
| KB do projeto (CRUD, Coverage, Versions, Export, Import, Rollback) | `@require_auth` | Consultor + Admin |
| `GET /api/GetSectorKB` | `@require_auth` | Consultor + Admin |
| `GET /api/GetSectorKBCoverage` | `@require_auth` | Consultor + Admin |
| `GET /api/GetSectorKBVersions` | `@require_auth` | Consultor + Admin |
| `GET /api/ExportSectorKB` | `@require_auth` | Consultor + Admin |
| `POST /api/PromoteToSectorKB` | `@require_admin` | Admin |
| `POST /api/ImportSectorKB` | `@require_admin` | Admin |
| `PUT /api/UpdateSectorKBEntry` | `@require_admin` | Admin |
| `DELETE /api/DeleteSectorKBEntry` | `@require_admin` | Admin |
| `POST /api/RollbackSectorKB` | `@require_admin` | Admin |
| `POST /api/AddSectorKBEntry` | `@require_admin` | Admin |
| `POST /api/CreateSector` | `@require_admin` | Admin |
| `PUT /api/UpdateSector` | `@require_admin` | Admin |
| `DELETE /api/DeleteSector` | `@require_admin` | Admin |
| Copilot endpoints | `@require_auth` | Consultor + Admin |
| ML legacy endpoints | `@require_auth` | Consultor + Admin |

## App Registration no Azure (Entra ID)

**Pré-requisito manual antes da implementação:**

1. Registrar 1 app no Entra ID (portal Azure)
2. Tipo: **SPA (Single Page Application)**
3. Redirect URIs:
   - `http://localhost:3000` (dev)
   - URL de produção do Static Web App
   - URLs de preview/staging se aplicável
4. Permissões: `User.Read` (Microsoft Graph — básico)
5. Token: access token com claims `preferred_username`, `name`, `email`
6. Anotar `AZURE_AD_TENANT_ID` e `AZURE_AD_CLIENT_ID` para as variáveis de ambiente

## Dev Local

- Login funciona localmente contra Entra ID real (redirect URI `http://localhost:3000`)
- Backend valida o mesmo JWT

### Bypass para testes automatizados

- Flag `SKIP_AUTH=true` bypassa validação JWT
- **Safeguard**: SKIP_AUTH só funciona quando `WEBSITE_SITE_NAME` NÃO está definido (essa variável só existe no Azure App Service/Functions em cloud). Se `WEBSITE_SITE_NAME` estiver definido, SKIP_AUTH é ignorado e logga WARNING. Isso é mais seguro que checar `AZURE_FUNCTIONS_ENVIRONMENT`, que pode defaultar para `Development` inclusive no Azure.

## Notas de Implementação (do plan-critic)

- `options_response()` precisa aceitar `req` como parâmetro para ecoar header `Origin`
- Considerar desabilitar CORS no `host.json` (`"allowedOrigins": []`) e tratar inteiramente na camada de aplicação para evitar conflito duplo
- `Access-Control-Max-Age: 3600` reduz preflight em endpoints polled frequentemente (`GetJobStatus`)

## Evolução Futura

- **Grupos Entra ID**: migrar `ADMIN_EMAILS` para grupo "SpendAnalysis-Admins" no Azure AD
- **Roles granulares**: adicionar roles por projeto (ex: consultor X só vê projetos atribuídos)
- **Audit trail**: logar quem fez cada operação com timestamp
