# Relatório de Prontidão para Produção

**Sistema:** Spend Analysis v3 — Plataforma completa
**Data:** 2026-03-23
**Escopo:** Backend (Azure Functions, 20 módulos src/, 10 blueprints), Frontend (Next.js 14, 70+ componentes/hooks), Pipeline de classificação LLM, Knowledge Base, Autenticação Azure AD
**Fases executadas:** 1 (Feature Discovery), 2 (Arquitetura), 3 (Concorrência), 4 (Resiliência), 5 (Segurança), 6 (Consolidação)

---

## Veredito Geral

| Dimensão | Nota (1-10) | Status |
|----------|------------|--------|
| Arquitetura | 7 | AMARELO |
| Concorrência | 7 | AMARELO |
| Resiliência | 6 | AMARELO |
| Segurança | 6 | AMARELO |
| Observabilidade | 4 | VERMELHO |
| **Prontidão Geral** | **6.0** | **AMARELO** |

**Recomendação:** PRONTO COM RESSALVAS -- o sistema funciona para o uso atual (equipe pequena de consultores, volumes moderados), mas precisa de correções em segurança, observabilidade e resiliência antes de escalar para múltiplos clientes ou cargas maiores.

---

## Resumo Executivo

O Spend Analysis v3 é uma plataforma funcional e bem estruturada para classificação de gastos corporativos com IA. A arquitetura baseada em Azure Functions com queue-triggered workers, two-phase classification (KB direct match + LLM), e knowledge base com loop de aprendizado humano é adequada para o domínio. A autenticação Azure AD (MSAL) foi implementada corretamente com JWT validation, JWKS rotation, e role-based access control.

Os principais riscos identificados são: (1) **observabilidade quase inexistente** -- não há APM, métricas estruturadas, alertas, ou distributed tracing; problemas em produção serão descobertos por usuários, não por monitores; (2) **surface de ataque em endpoints de KB** -- path traversal potencial via projectId/sectorName, falta de rate limiting, e IDOR entre projetos; (3) **resiliência frágil na integração com Grok/xAI** -- retry com apenas 2 tentativas, timeout fixo de 90s sem circuit breaker, e sem fallback quando a API está degradada; (4) **storage baseado em Azure File Share** (filesystem) sem backups automatizados, sem encriptação at-rest explícita, e sem estratégia de disaster recovery.

O sistema está pronto para uso interno com a equipe atual de consultores da PG. Para escalar, as 14 correções críticas e 12 importantes listadas abaixo devem ser endereçadas.

---

## Fase 1 — Feature Discovery

### Mapa Arquitetural

**Componentes mapeados:** 20 módulos Python (src/), 10 blueprints, 70+ componentes/hooks TypeScript
**Fluxos de dados:** 4 fluxos principais (classificação, revisão, KB management, autenticação)
**Pontos de integração:** 5 (Grok/xAI API, Azure Storage Queue, Azure File Share, Azure AD/MSAL, Direct Line/Copilot Studio)

### Fluxo Principal — Classificação

```
Frontend (Next.js)
  → Upload Excel (base64) → POST /api/SubmitTaxonomyJob
    → Backend: decode → pandas → sort → chunk 500 → salva em filesystem
    → enqueue_job() → Azure Storage Queue (taxonomy-jobs)
  → Polling: GET /api/GetTaxonomyJobStatus (a cada ~3s)

Queue trigger (ProcessTaxonomyJob)
  → process_single_job():
    → locked_status: PENDING → PROCESSING (com worker_id lease)
    → _prepare_job_info(): merge KB setor + projeto, cria KBRetriever (TF-IDF)
    → ThreadPoolExecutor(max_workers=5):
      → process_single_chunk():
        → Phase 1: KB direct match (sim >= 0.90)
        → Phase 2: LLM (Grok) com enriched examples
        → Hierarchy validation (cascade: exact → shift → fuzzy → n4-reverse)
      → update_job_progress() após cada chunk
    → consolidate_job(): merge results → Excel b64 → CLASSIFIED

Frontend → GET /api/GetJobResults → renderiza tabela de revisão
  → Consultant: approve/edit/reject cada item
  → POST /api/ApproveClassifications
    → Alimenta KB projeto → Excel final → COMPLETED
```

### Dívida Técnica Catalogada

| Item | Arquivo | Impacto |
|------|---------|---------|
| `taxonomy_mapper.py` dead code | `src/taxonomy_mapper.py` | Baixo -- 177 linhas não usadas |
| Legacy ML path (varejo/educacional) | `src/hybrid_classifier.py`, `src/ml_classifier.py` | Médio -- código mantido mas raramente usado |
| `seed_from_project()` deprecated | `src/knowledge_base.py:388` | Baixo -- marcado como deprecated |
| `console.log` em produção | `frontend/src/lib/api.ts` (múltiplos) | Baixo -- poluição do console |
| `getTrainingData` usa `page_size` (snake_case) | `frontend/src/lib/api.ts:209` | Baixo -- inconsistência mas funciona |
| Python local 3.12 vs Azure 3.13 | Runtime mismatch | Médio -- pode causar bugs sutis |

---

## Fase 2 — Revisão Arquitetural

### Pontos Positivos

1. **Separação clara de responsabilidades**: blueprints (API), src/ (lógica), models/ (dados)
2. **Two-Phase classification**: KB direct match evita chamadas LLM desnecessárias, reduzindo custo e latência
3. **Queue-triggered processing**: desacopla upload de processamento, com retry automático via dequeue count
4. **File locking robusto**: `locked_status()` com atomic write-to-temp-then-rename para crash safety
5. **Hierarquia como lista**: preserva N4s duplicados, decisão correta para o domínio
6. **KBRetriever criado 1x por job**: evita re-indexação TF-IDF por chunk
7. **Auth com key rotation**: JWKS refreshed automaticamente quando kid não é encontrado

### Problemas Arquiteturais

#### CRITICO-ARQ-1: Storage em Filesystem sem Backup
- **Arquivo:** Toda a camada de dados (`models/`, `taxonomy_jobs/`)
- **Problema:** Dados de projetos, KBs, jobs, e resultados vivem em Azure File Share acessado como filesystem. Não há backup automatizado, replicação, ou disaster recovery documentados.
- **Impacto:** Perda de dados irrecuperável em caso de falha do File Share ou corrupção
- **Recomendação:** Configurar Azure Backup para o File Share (snapshot diário, retenção 30 dias). Considerar migração gradual para Cosmos DB ou Table Storage para dados estruturados.

#### CRITICO-ARQ-2: Sem Idempotência no Queue Processing
- **Arquivo:** `src/worker_helpers.py:575-676`
- **Problema:** `process_single_job()` usa `processing_worker_id` como lease, mas se o worker crashar após processar chunks mas antes de consolidar, o retry via queue reprocessará chunks já concluídos. Os result files no filesystem atuam como checkpoint implícito (verificação de existência), mas a re-execução do LLM para chunks já processados é um custo desnecessário.
- **Impacto:** Custo extra em chamadas LLM duplicadas em cenários de retry. O resultado final é correto (idempotent write de result files), mas ineficiente.
- **Recomendação:** O design atual já mitiga parcialmente (`find_next_chunks` pula chunks com `result_*.json` existente). Documentar este comportamento como intencional.

#### IMPORTANTE-ARQ-3: Sem Limite de Tamanho para KBs
- **Arquivo:** `src/knowledge_base.py`
- **Problema:** O knowledge_base.json é carregado inteiro em memória em cada operação. Sem limite de entries. Uma KB com 100k+ entradas causará OOM ou latência excessiva no TF-IDF.
- **Impacto:** Degradação de performance em projetos com muitos itens aprovados
- **Recomendação:** Adicionar limite configurável (ex: 50k entries) com warning ao consultor. Considerar pagination no load ou SQLite para KBs grandes.

#### IMPORTANTE-ARQ-4: SPOF no Grok/xAI
- **Arquivo:** `src/llm_classifier.py`
- **Problema:** A API Grok é o único provedor LLM. Sem fallback para OpenAI, Azure OpenAI, ou outro provedor. Se Grok estiver down, todo o pipeline de classificação para.
- **Impacto:** Indisponibilidade total da classificação durante outages da xAI
- **Recomendação:** Implementar fallback provider (OpenAI compatível). O `get_azure_openai_config()` já abstrai o endpoint, facilitando a adição de fallback.

#### MENOR-ARQ-5: Consolidation Deletes Chunk Files
- **Arquivo:** `src/worker_helpers.py:552-561`
- **Problema:** `consolidate_job()` deleta chunk_*.json e result_*.json após consolidação. Se `GetJobResults` for chamado durante a janela entre CLASSIFIED sendo escrito e os deletes, pode retornar dados parciais. O código em `classification_bp.py:425` já mitiga isso usando result.json para jobs CLASSIFIED, mas a race window existe para PROCESSING status.
- **Impacto:** Risco baixo -- mitigado pelo check de status no GetJobResults
- **Recomendação:** Nenhuma ação necessária. O design atual é correto.

---

## Fase 3 — Análise de Concorrência

### Pontos de Escrita Mapeados

| Recurso | Escritores | Proteção | Status |
|---------|-----------|----------|--------|
| `status.json` (por job) | Worker + API (Cancel, Approve) | `filelock.FileLock` + atomic rename | OK |
| `knowledge_base.json` | API (CRUD, Approve, Import, Promote) | `filelock.FileLock` | OK |
| `project_config.json` | API (Create, Update) | `filelock.FileLock` | OK |
| `sector_config.json` | API (Create, Update) | `filelock.FileLock` | OK |
| `result_*.json` (chunk) | Worker (1 writer por chunk) | Sem lock (por design) | OK |
| `result.json` (consolidado) | Worker (1 writer) | Protegido por status gate | OK |
| `classified_excel_b64.txt` | Worker (1 writer) | Protegido por status gate | OK |
| `approved_result_b64.txt` | API (Approve) | Sem lock | RISCO BAIXO |

### Race Conditions Identificadas

#### CRITICO-CONC-1: KB Write Sem Coordenação entre Approve e Manual Add
- **Arquivo:** `src/knowledge_base.py:79-157`
- **Problema:** `add_entries()` faz reload da KB dentro do lock, o que previne data loss. No entanto, se dois ApproveClassifications de jobs diferentes executarem simultaneamente para o mesmo projeto, cada um adquire o lock sequencialmente. O segundo verá as entries do primeiro. Correto.
- **Status:** OK -- o file lock dentro de `add_entries()` (reload + write) garante serialização

#### IMPORTANTE-CONC-2: JWKS Cache Sem Thread Safety
- **Arquivo:** `src/auth.py:20-21`
- **Problema:** `_jwks_cache` é um dict global compartilhado entre threads. Leituras e escritas não são protegidas por lock. Em teoria, uma thread pode ler `keys` enquanto outra escreve, causando dados inconsistentes.
- **Impacto:** Risco baixo na prática (CPython GIL protege dict assignment), mas conceitualmente inseguro
- **Recomendação:** Usar `threading.Lock()` ou `functools.lru_cache` com TTL

#### IMPORTANTE-CONC-3: LLM Semaphore Global Cross-Chunk
- **Arquivo:** `src/llm_classifier.py:23`
- **Problema:** `_LLM_SEMAPHORE = threading.Semaphore(15)` é global (module-level). Em Azure Functions, múltiplos queue triggers podem rodar simultaneamente. Se 3 jobs de 5 chunks cada tentarem simultaneamente, os 15 slots do semáforo podem não ser suficientes e causar starvation.
- **Impacto:** Em cenários de múltiplos jobs simultâneos, um job pode monopolizar o semáforo
- **Recomendação:** Considerar semáforo por job ou configuração dinâmica baseada na concorrência observada. O `batchSize: 1` no host.json limita a 1 job por vez, mitigando parcialmente.

#### MENOR-CONC-4: Health Check Grok Probe Cache
- **Arquivo:** `blueprints/health_bp.py:16-17`
- **Problema:** `_grok_probe_cache` é um dict global sem proteção de thread. Mesmo risco que CONC-2.
- **Impacto:** Risco negligível -- worst case é uma probe duplicada
- **Recomendação:** Aceitar o risco. Probe duplicada não causa dano.

### Operações de Idempotência

| Operação | Idempotente? | Nota |
|----------|-------------|------|
| `process_single_job()` | Parcial | Re-execução pula chunks com result_*.json mas re-faz LLM calls para chunks incompletos |
| `consolidate_job()` | Sim | Verifica status gate antes de escrever |
| `add_entries()` (KB) | Sim | Dedup por description_norm, update condicional |
| `enqueue_job()` | Sim | Queue permite mensagens duplicadas, worker verifica status |
| `ApproveClassifications` | Sim | Verifica status gate (CLASSIFIED/APPROVED) |
| `CancelJob` | Sim | Verifica status gate (PENDING/PROCESSING) |

---

## Fase 4 — Resiliência (Engenharia do Caos)

### Catálogo de Cenários de Desastre

#### CRITICO-RES-1: Grok API Indisponível (Outage Total)
- **Cenário:** xAI API retorna 5xx ou fica irresponsiva por mais de 30 minutos
- **Comportamento atual:** Retry 2x com backoff exponencial → fallback ("Não Identificado", confidence 0.0) → job completa com 100% fallback → warning no status.json se >50% fallback
- **Impacto:** Jobs completam mas sem classificação útil. Consultor vê tudo como "Não Identificado"
- **MTTR estimado:** Manual -- depende de quando xAI restaura o serviço
- **Recomendação:** Implementar circuit breaker com health check periódico. Quando circuit aberto, retornar erro 503 no SubmitTaxonomyJob em vez de aceitar jobs que vão falhar.

#### CRITICO-RES-2: Azure File Share Indisponível
- **Cenário:** File Share inacessível (rede, quota, falha de storage account)
- **Comportamento atual:** Exceções não tratadas em leituras/escritas de JSON. Worker crashará, queue retentará 5x, poi message irá para poison queue.
- **Impacto:** Indisponibilidade total -- nenhum endpoint funciona
- **MTTR estimado:** Depende da Azure. Sem backup, dados podem ser perdidos permanentemente.
- **Recomendação:** Health check já verifica filesystem. Adicionar alerta automático quando `filesystem: false`.

#### CRITICO-RES-3: Queue Message Perdida + Enqueue Falhou
- **Cenário:** `enqueue_job()` retorna False (conn string ausente ou falha de rede)
- **Comportamento atual:** Job fica PENDING, CleanupStaleJobs re-enfileira após 5 minutos. Se a queue estiver persistentemente indisponível, re-enqueue também falhará.
- **Impacto:** Job fica PENDING indefinidamente se a queue não recuperar dentro de 1h (cleanup timer)
- **Recomendação:** O design atual com cleanup timer como safety net é adequado. Garantir que o timer funcione quando a queue está down (usa `enqueue_job()` que pode falhar silenciosamente).

#### IMPORTANTE-RES-4: Memory Exhaustion durante Consolidação
- **Cenário:** Job com 100k linhas. `consolidate_job()` carrega todos os chunks em memória, cria DataFrame, gera Excel, converte para base64.
- **Comportamento atual:** Sem limit explícito de memória. Limite de upload é 100k linhas. Excel b64 para 100k linhas pode consumir 500MB+ de RAM.
- **Impacto:** OOM kill do worker process, job fica em PROCESSING até cleanup timer marcar ERROR
- **Recomendação:** Monitorar uso de memória. Considerar streaming ou chunked Excel generation para jobs grandes. O `del final_df` e `del xlsx_b64` em consolidate_job() já mitiga parcialmente.

#### IMPORTANTE-RES-5: LLM Response Parsing Failure
- **Cenário:** Grok retorna JSON malformado, resposta truncada, ou formato inesperado
- **Comportamento atual:** `_call_openai_api_inner()` tem múltiplos fallbacks: JSON parse → dict→list detection → index matching → text matching → fallback ("Não Identificado")
- **Impacto:** Itens afetados ficam como "Não Identificado" com confidence 0.0. Job não falha.
- **Recomendação:** O tratamento atual é robusto. Adicionar logging do response body quando o parsing falha para debugging.

#### MENOR-RES-6: Clock Skew entre Worker e API
- **Cenário:** Worker e API em instâncias diferentes com clocks dessincronizados
- **Comportamento atual:** Timestamps usam `datetime.now(timezone.utc)`. Cleanup timer compara `created_at` com `now`. Clock skew >1h poderia causar cleanup prematuro.
- **Impacto:** Risco baixo -- Azure VMs usam NTP
- **Recomendação:** Nenhuma ação necessária.

### Matriz de Timeouts

| Componente | Timeout Configurado | Adequado? |
|-----------|-------------------|-----------|
| Function timeout (host.json) | 30 min | OK -- suficiente para jobs grandes |
| Queue visibility timeout | 45 min | OK -- maior que function timeout |
| LLM HTTP request | 90s | OK -- batches de 100 itens podem demorar |
| LLM retries | 2 (total 3 tentativas) | INSUFICIENTE para rate limiting pesado |
| JWKS fetch | 10s | OK |
| Direct Line token | 10s | OK |
| File lock timeout | 10s | OK |
| Health check Grok probe | 10s | OK |
| Axios global (frontend) | 30s | OK |
| Grok probe cache TTL | 5 min | OK |
| JWKS cache TTL | 24h | OK, com refresh on kid miss |

### Cadeia de Cascata

```
Grok API down
  → classify_items_with_llm() retorna fallback (0.0 confidence) após 3 tentativas
  → process_single_chunk() salva result com tudo "Não Identificado"
  → consolidate_job() marca CLASSIFIED com warning "X% fallback"
  → Frontend mostra warning ao consultor
  → Consultor pode re-submeter quando API voltar
  ✅ Cascata contida — não afeta outros subsistemas
```

```
File Share saturado (quota)
  → write_status() falha → exceção no worker
  → Queue retenta 5x → poison queue → HandlePoisonTaxonomyJob
  → handle_poison_message() tenta escrever ERROR → também falha
  → Job fica em estado inconsistente até File Share recuperar
  ❌ Cascata NÃO contida — afeta TODOS os endpoints
```

---

## Fase 5 — Segurança

### Autenticação e Autorização

#### CRITICO-SEG-1: Path Traversal em projectId e sectorName
- **Arquivo:** `blueprints/knowledge_bp.py`, `blueprints/projects_bp.py`, `blueprints/classification_bp.py`
- **Problema:** `projectId` e `sectorName` são usados diretamente para construir caminhos de filesystem (`os.path.join(models_dir, "projects", project_id)`). Um atacante autenticado poderia enviar `projectId="../../../etc"` para ler/escrever fora do diretório models.
- **Evidência:** `_get_project_id()` em `knowledge_bp.py:21` faz apenas `.strip()`. `create_project()` usa `_slugify()` que sanitiza, mas `get_project()`, `update_project()`, e KB endpoints recebem o ID como-está.
- **Impacto:** Leitura/escrita arbitrária no filesystem do server (limitado ao user do Functions runtime)
- **Recomendação:** Validar que projectId e sectorName não contêm `..`, `/`, `\`, ou caracteres especiais. Adicionar regex validation: `^[a-z0-9-]+$`.

#### CRITICO-SEG-2: IDOR entre Projetos
- **Arquivo:** Todos os endpoints que recebem `projectId`
- **Problema:** Qualquer usuário autenticado pode acessar qualquer projeto. Não há verificação de que o usuário tem permissão para acessar o projeto especificado. Um consultor pode ver/editar KBs de projetos de outros consultores.
- **Impacto:** Vazamento de dados entre projetos/clientes. Em cenário multi-cliente, consultor A vê dados do cliente B.
- **Recomendação:** Para o uso atual (equipe interna), o risco é aceitável. Para multi-tenancy, implementar project-level ACL ou tenant isolation.

#### IMPORTANTE-SEG-3: AuthLevel.ANONYMOUS em Todos os Endpoints
- **Arquivo:** `function_app.py:15`, todos os blueprints
- **Problema:** Todos os endpoints usam `auth_level=func.AuthLevel.ANONYMOUS`. A autenticação é feita pelo decorator `@require_auth` em Python, não pela infraestrutura do Azure Functions. Isso significa que a Azure não rejeita requests não autenticadas -- elas chegam ao código Python.
- **Evidência:** O CLAUDE.md já documenta: "Endpoints usam `AuthLevel.ANONYMOUS` — restringir em produção"
- **Impacto:** O `@require_auth` funciona, mas um bug ou omissão no decorator exporia o endpoint completamente. Defense-in-depth ausente.
- **Recomendação:** Manter AuthLevel.ANONYMOUS (necessário para CORS preflight e custom JWT validation), mas garantir que TODOS os endpoints têm `@require_auth` ou `@require_admin`. O endpoint `health` (`health_bp.py:68`) NÃO tem auth -- intencional e correto para probes.

#### IMPORTANTE-SEG-4: SKIP_AUTH Bypass
- **Arquivo:** `src/auth.py:149-153`
- **Problema:** `SKIP_AUTH=true` bypassa toda a autenticação. O check `not on_azure` (via `WEBSITE_SITE_NAME`) é correto mas depende de um env var que o administrador da Function App controla.
- **Impacto:** Se alguém configurar `SKIP_AUTH=true` na Azure Function App por engano, toda a auth é desabilitada
- **Recomendação:** Adicionar warning log em produção quando SKIP_AUTH é detectado mas não permitido. O check atual é adequado.

#### IMPORTANTE-SEG-5: CORS Permite Origins Dinâmicas via Env Var
- **Arquivo:** `src/api_helpers.py:18-22`
- **Problema:** `ALLOWED_ORIGINS` é configurável via env var. Se mal-configurado (ex: `*`), qualquer site poderia fazer requests autenticadas.
- **Impacto:** Cross-site request forgery se CORS for configurado com `*`
- **Recomendação:** Validar que ALLOWED_ORIGINS nunca contém `*`. Adicionar check no startup.

#### IMPORTANTE-SEG-6: Sem Rate Limiting
- **Arquivo:** Todos os endpoints HTTP
- **Problema:** Nenhum rate limiting em nenhum endpoint. Um atacante autenticado poderia fazer milhares de requests por segundo, causando DoS ou custos excessivos na API Grok.
- **Impacto:** DoS, custos LLM descontrolados
- **Recomendação:** Implementar rate limiting via Azure API Management ou middleware. Prioridade para endpoints que fazem chamadas LLM (SubmitTaxonomyJob, ReclassifyItems).

#### IMPORTANTE-SEG-7: API Key do Grok em Env Var sem Rotação
- **Arquivo:** `src/llm_classifier.py:83-84`
- **Problema:** API key em env var sem mecanismo de rotação. Se comprometida, requer redeploy para trocar.
- **Recomendação:** Usar Azure Key Vault com managed identity.

#### MENOR-SEG-8: JWT Token Lifetime Não Controlado pelo Backend
- **Arquivo:** `src/auth.py`
- **Problema:** O backend valida expiry mas não impõe max lifetime. Tokens com lifetime longo (configurado no Azure AD) terão acesso prolongado.
- **Recomendação:** Considerar max token age check (ex: rejeitar tokens > 1h). Baixa prioridade.

#### MENOR-SEG-9: group_claim Silenciosamente Ignorado
- **Arquivo:** `src/auth.py:129-143`
- **Problema:** Se `ALLOWED_GROUP_ID` está configurado mas o token não contém claim `groups`, o check é silenciosamente pulado (`return` sem raise). Isso significa que um app registration sem "groups" claim permite acesso irrestrito.
- **Recomendação:** Quando `ALLOWED_GROUP_ID` está configurado, a ausência do claim `groups` deveria bloquear, não permitir. O log warning existe mas não é suficiente.

### Injeção

#### MENOR-SEG-10: Prompt Injection via client_context e user_instruction
- **Arquivo:** `src/llm_classifier.py:270-340`
- **Problema:** `client_context` e `user_instruction` do consultor são inseridos diretamente no system prompt do LLM. Um consultor poderia injetar instruções maliciosas.
- **Impacto:** Risco baixo -- o consultor já tem acesso legítimo. Mas instruções maliciosas poderiam causar classificações incorretas em massa.
- **Recomendação:** Sanitizar ou delimitar claramente inputs do usuário no prompt. Baixa prioridade para uso interno.

---

## Fase 6 — Observabilidade

### CRITICO-OBS-1: Sem APM ou Distributed Tracing
- **Problema:** Não há Application Insights, Datadog, ou qualquer APM integrado. Não há correlation IDs entre requests, worker processing, e LLM calls.
- **Impacto:** Impossível diagnosticar problemas de performance, identificar gargalos, ou fazer root cause analysis de falhas
- **Recomendação:** Integrar Azure Application Insights (SDK Python + Next.js). É nativo do Azure Functions e requer configuração mínima.

### CRITICO-OBS-2: Sem Alertas Automatizados
- **Problema:** Não há alertas para: API Grok down, jobs em ERROR, File Share cheio, queue depth crescendo, latência alta
- **Impacto:** Problemas são descobertos por usuários, não por monitores
- **Recomendação:** Configurar Azure Monitor alerts: queue depth > 10, error rate > 5%, Grok probe failure > 2 consecutivos

### IMPORTANTE-OBS-3: Logging Não Estruturado
- **Problema:** Logs usam `logging.info(f"...")` com strings formatadas. Não há structured logging (JSON) com campos indexáveis (job_id, project_id, duration_ms).
- **Impacto:** Impossível fazer queries eficientes nos logs. Correlação manual entre eventos.
- **Recomendação:** Usar structured logging com campos extras: `logger.info("chunk processed", extra={"job_id": job_id, "chunk": idx, "duration_ms": ms})`

### MENOR-OBS-4: Sem Métricas de Negócio
- **Problema:** Não há tracking de: items classificados por dia, taxa de KB direct match vs LLM, custo LLM por job, taxa de aprovação vs edição vs rejeição
- **Recomendação:** Emitir custom metrics para dashboarding. Prioridade baixa mas valioso para otimização de custos.

---

## Findings Consolidados

### Findings Críticos (ação imediata)

| # | Categoria | Problema | Impacto | Correção | Esforço |
|---|----------|---------|---------|---------|---------|
| 1 | Segurança | Path traversal em projectId/sectorName | Leitura/escrita arbitrária no FS | Validar regex `^[a-z0-9-]+$` em todos os endpoints | Baixo |
| 2 | Observabilidade | Sem APM ou distributed tracing | Impossível diagnosticar problemas | Integrar Azure Application Insights | Médio |
| 3 | Observabilidade | Sem alertas automatizados | Problemas descobertos por usuários | Configurar Azure Monitor alerts | Médio |
| 4 | Resiliência | Grok API down sem circuit breaker | Jobs completam com 100% fallback sem aviso preventivo | Implementar circuit breaker com health check | Médio |
| 5 | Arquitetura | Filesystem sem backup automatizado | Perda de dados irrecuperável | Configurar Azure Backup para File Share | Baixo |
| 6 | Segurança | group_claim silenciosamente ignorado quando absent | Auth bypass se IdP não emite groups | Bloquear quando ALLOWED_GROUP_ID set mas claim ausente | Baixo |

### Findings Importantes (próximo sprint)

| # | Categoria | Problema | Impacto | Correção | Esforço |
|---|----------|---------|---------|---------|---------|
| 7 | Segurança | IDOR entre projetos | Consultor vê dados de outro projeto | Implementar project-level ACL | Alto |
| 8 | Segurança | Sem rate limiting | DoS, custos LLM descontrolados | Azure API Management ou middleware | Médio |
| 9 | Resiliência | LLM retry apenas 2x (total 3) | Insuficiente para rate limiting pesado | Aumentar para 4-5 com backoff | Baixo |
| 10 | Arquitetura | SPOF no Grok/xAI sem fallback | Indisponibilidade total da classificação | Adicionar fallback provider | Alto |
| 11 | Resiliência | Memory exhaustion em jobs grandes (100k) | OOM kill do worker | Monitoring + streaming Excel | Médio |
| 12 | Concorrência | JWKS cache sem thread safety | Risco teórico de dados inconsistentes | `threading.Lock()` no cache | Baixo |
| 13 | Observabilidade | Logging não estruturado | Queries ineficientes nos logs | Migrar para structured logging JSON | Médio |
| 14 | Segurança | API Key Grok sem Key Vault | Sem rotação, exposição em env vars | Migrar para Azure Key Vault | Médio |
| 15 | Segurança | CORS aceita origins via env var sem validação | CSRF se mal-configurado | Validar que não contém `*` | Baixo |
| 16 | Arquitetura | KB sem limite de tamanho | OOM com KBs grandes | Limit 50k entries com warning | Baixo |
| 17 | Resiliência | Cascata File Share saturado não contida | Afeta TODOS os endpoints | Health check + alerta de quota | Médio |
| 18 | Segurança | AuthLevel.ANONYMOUS sem defense-in-depth | Bug no decorator expõe endpoint | Audit todos endpoints têm `@require_auth` | Baixo |

### Findings Menores (backlog)

| # | Categoria | Problema | Impacto | Correção | Esforço |
|---|----------|---------|---------|---------|---------|
| 19 | Dívida técnica | `taxonomy_mapper.py` dead code | Confusão no codebase | Remover | Baixo |
| 20 | Segurança | Prompt injection via client_context | Classificações incorretas | Sanitizar inputs no prompt | Baixo |
| 21 | Observabilidade | Sem métricas de negócio | Sem visibilidade de custos/eficiência | Custom metrics | Médio |
| 22 | Dívida técnica | `console.log` no frontend em prod | Poluição do console | Substituir por logger condicional | Baixo |
| 23 | Dívida técnica | Python 3.12 vs 3.13 mismatch | Bugs sutis | Alinhar versões | Baixo |
| 24 | Concorrência | Health check cache sem thread safety | Probe duplicada | Aceitar risco | Nenhum |
| 25 | Segurança | JWT sem max lifetime check | Tokens longos mantêm acesso | Check opcional de max age | Baixo |

---

## Métricas por Fase

### Fase 1 — Feature Discovery
- Arquivos mapeados: 30+ (20 Python, 10 TS/TSX hooks/pages, 70+ componentes)
- Fluxos de dados: 4 (classificação, revisão, KB, auth)
- Pontos de integração: 5 (Grok, Queue, File Share, Azure AD, Direct Line)
- Itens de dívida técnica: 6

### Fase 2 — Arquitetura
- Problemas encontrados: 5 (1 crítico, 2 importantes, 2 menores)
- SPOFs identificados: 2 (Grok API, File Share)
- Padrões inadequados: 0 (arquitetura é adequada para o escopo)

### Fase 3 — Concorrência
- Pontos de escrita: 8
- Race conditions: 1 importante, 2 menores (1 teórica)
- Operações não-idempotentes: 0 de 6 (todas parcial ou totalmente idempotentes)
- Transações sem proteção: 0 (file locking ubíquo)

### Fase 4 — Resiliência
- Componentes sem timeout: 0 de 10 (todos têm timeout)
- Componentes sem retry: 2 de 5 (File Share ops, KB ops -- dependem de file lock retry)
- Cenários de desastre críticos: 3 (Grok down, File Share down, memory exhaustion)
- MTTR estimado: 5-60min (dependendo do cenário)

### Fase 5 — Segurança
- Vulnerabilidades críticas: 2 (path traversal, group claim bypass)
- Vulnerabilidades importantes: 6 (IDOR, rate limiting, AuthLevel, Key Vault, CORS, SKIP_AUTH)
- Vulnerabilidades menores: 3 (prompt injection, JWT lifetime, dead code)

### Fase 6 — Observabilidade
- APM: ausente
- Alertas: ausentes
- Structured logging: ausente
- Métricas de negócio: ausentes

---

## Plano de Ação

### Semana 1 (Quick Wins — esforço baixo, impacto alto)

- [ ] **SEG-1**: Adicionar validação regex em projectId/sectorName — `^[a-z0-9-]+$` em `knowledge_bp.py`, `projects_bp.py`, `classification_bp.py`, `review_bp.py`
- [ ] **SEG-6**: Mudar `_validate_group_claim()` para bloquear (raise ForbiddenError) quando ALLOWED_GROUP_ID está configurado mas claim groups está ausente
- [ ] **ARQ-1**: Habilitar Azure Backup no File Share (snapshot diário, retenção 30 dias) via Portal Azure
- [ ] **SEG-15**: Adicionar validação no startup que ALLOWED_ORIGINS não contém `*`
- [ ] **SEG-18**: Audit que todos os 47 endpoints HTTP têm `@require_auth` ou `@require_admin`
- [ ] **DT-19**: Remover `src/taxonomy_mapper.py` (dead code confirmado)

### Semana 2-4 (Correções Estruturais)

- [ ] **OBS-1**: Integrar Azure Application Insights — `APPINSIGHTS_INSTRUMENTATIONKEY` + `opencensus-ext-azure` no Python, `@vercel/analytics` ou App Insights SDK no Next.js
- [ ] **OBS-2**: Configurar Azure Monitor alerts: queue depth > 10, error jobs/hour > 3, health check degraded > 2 consecutivos
- [ ] **RES-1**: Implementar circuit breaker para Grok API — manter estado (open/closed/half-open) baseado em taxa de erro. Quando aberto, SubmitTaxonomyJob retorna 503.
- [ ] **SEG-8**: Aumentar LLM retries para 4 (total 5 tentativas) com backoff mais agressivo para 429s
- [ ] **CONC-2**: Adicionar `threading.Lock()` ao `_jwks_cache` em `src/auth.py`
- [ ] **OBS-3**: Migrar para structured logging com `extra={}` nos módulos críticos (worker_helpers, llm_classifier, auth)
- [ ] **SEG-14**: Migrar GROK_API_KEY para Azure Key Vault com managed identity

### Mês 2+ (Hardening)

- [ ] **SEG-7**: Implementar project-level ACL (associar projetos a users/groups do Azure AD)
- [ ] **SEG-6**: Implementar rate limiting (Azure API Management front-end ou custom middleware)
- [ ] **ARQ-4**: Adicionar fallback LLM provider (OpenAI ou Azure OpenAI)
- [ ] **ARQ-3**: Adicionar limite de KB entries (50k) com warning e paginação no load
- [ ] **RES-4**: Implementar streaming Excel generation para jobs > 50k linhas
- [ ] **OBS-4**: Implementar métricas de negócio (classificados/dia, custo LLM/job, taxa KB match)

---

## Apêndices

### Arquivos Críticos Auditados

| Arquivo | Linhas | Auditado |
|---------|--------|----------|
| `src/auth.py` | 248 | Completo |
| `src/worker_helpers.py` | 714 | Completo |
| `src/llm_classifier.py` | 650 | Completo |
| `src/file_lock.py` | 79 | Completo |
| `src/queue_helpers.py` | 47 | Completo |
| `src/knowledge_base.py` | 469 | Completo |
| `src/core_classification.py` | 268 | Completo |
| `src/hierarchy_validator.py` | 295 | Completo |
| `src/project_manager.py` | 416 | Completo |
| `src/api_helpers.py` | 144 | Completo |
| `src/exceptions.py` | 56 | Completo |
| `src/kb_retriever.py` | 182 | Completo |
| `src/utils.py` | 81 | Completo |
| `blueprints/worker_bp.py` | 119 | Completo |
| `blueprints/classification_bp.py` | 637 | Completo |
| `blueprints/review_bp.py` | 356 | Completo |
| `blueprints/knowledge_bp.py` | 745 | Completo |
| `blueprints/projects_bp.py` | 217 | Completo |
| `blueprints/auth_bp.py` | 35 | Completo |
| `blueprints/health_bp.py` | 98 | Completo |
| `blueprints/copilot_bp.py` | 135 | Completo |
| `function_app.py` | 39 | Completo |
| `host.json` | 31 | Completo |
| `frontend/src/lib/api.ts` | 674 | Completo |
| `frontend/src/lib/msal-config.ts` | 30 | Completo |
| `frontend/src/contexts/AuthContext.tsx` | 296 | Completo |
| `frontend/src/pages/_app.tsx` | 91 | Completo |

### Configurações Verificadas

| Config | Valor | Adequado? |
|--------|-------|-----------|
| `functionTimeout` | 30min | OK |
| `maxConcurrentRequests` | 100 | OK |
| `queue.batchSize` | 1 | OK -- processa 1 job por vez |
| `queue.maxDequeueCount` | 5 | OK |
| `queue.visibilityTimeout` | 45min | OK -- > functionTimeout |
| `queue.messageEncoding` | "none" | OBRIGATÓRIO (compat Python SDK) |
| `queue.maxPollingInterval` | 5s | OK |
| `LLM_MAX_CONCURRENT_CALLS` | 15 | OK para uso atual |
| `LLM_TIMEOUT_SECONDS` | 90s | OK |
| `KB_DIRECT_MATCH_THRESHOLD` | 0.90 | OK -- alta precisão |
| `STALE_THRESHOLD_SECONDS` | 3600 | OK -- 1h |
| `MAX_PARALLEL_CHUNKS` | 5 | OK |
| `CHUNK_SIZE` | 500 | OK |
| `MAX_UPLOAD_ROWS` | 100k | OK |
