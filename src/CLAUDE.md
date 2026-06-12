# Backend — Módulos e Gotchas

## Módulos

| Arquivo | Responsabilidade |
|---------|-----------------|
| `exceptions.py` | Hierarquia de exceções de domínio (`SpendAnalysisError` → `NotFoundError`, `ValidationError`, `ConflictError`, `ExternalServiceError` → `BillingError`) |
| `auth.py` | Autenticação JWT Azure AD: `@require_auth`, `@require_admin`, JWKS cache, group claim validation |
| `validation.py` | `safe_resource_id()` — sanitização de IDs contra path traversal, null bytes, oversized inputs |
| `api_helpers.py` | `json_response()`, `error_response()`, `options_response()`, `@handle_errors`, `@rate_limit` decorators + security headers |
| `types.py` | TypedDict definitions (`KBEntryDict`, `ClassificationResultDict`, `JobStatusDict`, etc.) |
| `utils.py` | `get_models_dir()`, `safe_json_dumps()`, `friendly_source_label()`, `INCOMPLETE_VALUES` |
| `file_lock.py` | Thread-safe status.json: `read_status`, `write_status`, `update_status`, `locked_status` (ctx mgr). Usa `filelock` (pinado — ver Problemas Conhecidos no CLAUDE.md raiz). `_acquire_lock()` trata `PermissionError` (EACCES do flock em CIFS) como "lock ocupado" e tenta de novo dentro do budget de 10s; budget esgotado → `filelock.Timeout` (HTTP: 503 + Retry-After via `@handle_errors`) |
| `project_manager.py` | CRUD setores/projetos, `resolve_hierarchy()`, `delete_sector()` |
| `knowledge_base.py` | KB class (projeto + setor): CRUD, versões, cobertura, merge, promote |
| `kb_retriever.py` | TF-IDF cosine similarity para few-shot |
| `core_classification.py` | Two-Phase pipeline (KB match + LLM) ou ML+Dict+LLM (legado) |
| `queue_helpers.py` | `enqueue_job(job_id)` — envia mensagem para Azure Storage Queue `taxonomy-jobs`. Fallback gracioso (cleanup timer é safety net) |
| `worker_helpers.py` | `process_single_job()` (queue path), `_prepare_job_info()` (shared), cleanup, process_chunk, consolidate. `get_active_jobs()`/`run_worker_cycle()` DEPRECATED |
| `llm_classifier.py` | Grok/xAI (async, 15 workers) + few-shot + instrução + circuit breaker + billing fail-fast (`check_llm_health`, `BillingError` em 401/403) |
| `hierarchy_validator.py` | Validação cascata pós-LLM (exact → shift → fuzzy → n4-reverse) |
| `preprocessing.py` | `normalize_text()`, `build_tfidf_vectorizer()` |
| `taxonomy_engine.py` | Dicionário (regex/keywords) + analytics (Pareto) |
| `ml_classifier.py` | Preditor ML legado (TF-IDF + LogisticRegression) |
| `model_trainer.py` | Treinamento com versionamento |
| `memory_engine.py` | MemoryEngine — persistência de regras e contexto para Copilot |
| `hybrid_classifier.py` | Classificador legado (ML+Dict+LLM) — usado apenas por setores `varejo`/`educacional` via `use_legacy_ml=True`. Import lazy em `core_classification.py:202` |

## Constantes

```python
CHUNK_SIZE = 500                   # worker_helpers — linhas por chunk
MAX_PARALLEL_CHUNKS = 5            # chunks paralelos por job (ThreadPoolExecutor)
STALE_THRESHOLD_SECONDS = 3600     # PROCESSING sem progresso > 1h → cleanup re-enfileira
WORKER_DEADLINE_SECONDS = 1500     # 25min — parada limpa + self-re-enqueue (functionTimeout: 40min)
LEASE_STALE_SECONDS = 600          # 10min sem heartbeat → outro worker pode roubar o lease
MAX_RESUME_ATTEMPTS = 3            # retomadas via cleanup antes de marcar ERROR

LLM_BATCH_SIZE = 100               # itens por chamada Grok
LLM_MAX_CONCURRENT_CALLS = 15      # max chamadas LLM simultâneas (global, Semaphore)
LLM_TIMEOUT_SECONDS = 90
LLM_MAX_RETRIES = 2                # backoff exponencial

KB_DIRECT_MATCH_THRESHOLD = 0.90   # Phase 1: match sem LLM
KB_ENRICHED_EXAMPLE_MIN_SIM = 0.30 # Phase 2: mín para incluir como exemplo
KB_ENRICHED_MAX_EXAMPLES = 20      # max exemplos enriched por batch
FEW_SHOT_MAX_EXAMPLES = 10         # representativos globais
FEW_SHOT_PER_ITEM_K = 5            # top-K na reclassificação

CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5  # falhas consecutivas para abrir
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 60  # segundos antes de tentar HALF_OPEN

RATE_LIMIT_SUBMIT_JOB = 10/60     # SubmitTaxonomyJob: 10 req/min/IP

ML_CONFIDENCE_UNIQUE = 0.45        # legado
ML_CONFIDENCE_AMBIGUOUS = 0.25     # legado
```

## Schemas

### project_config.json
```json
{
  "project_id": "naval-wartsila",
  "display_name": "Naval - WÄRTSILÄ",
  "sector": "naval",
  "client_context": "Contexto do cliente para prompt LLM",
  "custom_hierarchy": [],
  "hierarchy_source": "own | padrao",
  "use_sector_kb": true,
  "few_shot_max_examples": 5
}
```

### knowledge_base.json (array)
```json
[{
  "id": "uuid",
  "description": "texto original",
  "description_norm": "texto normalizado",
  "N1": "...", "N2": "...", "N3": "...", "N4": "...",
  "source": "llm_approved | consultant_correction | reclassified_with_guidance",
  "confidence": 0.85,
  "version": "v1"
}]
```

## Blueprints — Endpoints

| Blueprint | Endpoints | Nota |
|-----------|----------|------|
| `projects_bp.py` | 9 (CRUD setores + projetos, DeleteSector) | |
| `classification_bp.py` | 5 (SubmitJob, GetStatus, GetJobResults, CancelJob, DownloadJobExcel) | |
| `review_bp.py` | 2 (ReclassifyItems, ApproveClassifications) | |
| `knowledge_bp.py` | 19 (KB projeto + setor: CRUD, coverage, versões, import/export, promote) | `entity_type="sector"` para setor |
| `models_bp.py` | 6 (ML legado) | |
| `copilot_bp.py` | 3 (Direct Line) | |
| `worker_bp.py` | 2 (ProcessTaxonomyJob queue trigger + CleanupStaleJobs timer 1h) | |
| `health_bp.py` | 1 (HealthCheck GET) | filesystem + grok checks |

## Gotchas Backend

### Classificação
- **Sort antes de chunking** — ordenar por `desc_col` (case-insensitive) agrupa similares no mesmo batch LLM. Não remover
- **Two-Phase**: (1) KB direct match ≥0.90 sem LLM; (2) restante vai ao LLM com enriched examples
- **KB direct match NÃO aplica na reclassificação** — consultor quer re-classificar com instrução, não match automático
- **`select_enriched_examples` limita 3 por N4** — garante diversidade. Sem o cap, exemplos ficam homogêneos
- **Prompts Grok**: exemplos confirmados ANTES da instrução do consultor. Não alterar ordem
- **`_llm_direct_pipeline()` não emite `status`/`matched_terms`** — retorna apenas description, N1-N4, source, confidence. `GetJobResults` deriva `status` dos N1-N4

### Knowledge Base
- **KB mesclada carregada 1x por job** — `_prepare_job_info()` faz merge e armazena em `job_info["kb_entries"]`. Chunks não recarregam
- **Merge usa `description_norm` como chave** — projeto sobrescreve setor
- **`add_entries()` dedup por `description_norm`** — cada descrição tem 1 entrada. Atualiza in-place se fonte mais autoritativa (consultant > reclassified > llm)
- **`ApproveClassifications` alimenta KB do projeto** — promoção para setor é ação separada via `PromoteToSectorKB`
- **KnowledgeBase `entity_type`**: `"project"` (default) ou `"sector"` — path automático, mesmos métodos

### Worker e Consolidação
- **Queue trigger**: `ProcessTaxonomyJob` recebe `{job_id}` da queue `taxonomy-jobs`, chama `process_single_job()` que processa 1 job completo (PENDING→CLASSIFIED)
- **Retry via queue**: erro genérico → `process_single_job()` NÃO escreve ERROR — limpa o próprio lease (`processing_worker_id`, guardado por `== worker_id`) e re-levanta exceção para retry da queue (maxDequeueCount=5) → poison. Lease limpo = o retry re-claima imediatamente, sem esperar os 10min de staleness. Atenção: o retry de mensagem falhada só fica visível após o `visibilityTimeout` da queue (45min, host.json). Exceções que retornam normal: deadline (self-re-enqueue), `BillingError` (ERROR explícito), cancel
- **Deadline cooperativo (25min)**: worker para limpo antes do functionTimeout (40min) — limpa o lease, re-enfileira `{job_id}` e retorna sucesso; o próximo slice retoma via `find_next_chunks`
- **Lease com heartbeat**: claim grava `processing_worker_id` + `lease_renewed_at`; renovado a cada chunk (`update_job_progress`). Lease >10min stale → outro worker ROUBA e retoma; lease fresco → skip (idempotência preservada)
- **Billing fail-fast**: pre-flight `check_llm_health()` (GET /v1/models) ao claimar o job + `BillingError` in-flight (401/403, sem retry) → job ERROR imediato com mensagem explícita "créditos xAI esgotados"
- **`classify_items_with_llm` retorna tuple** `(results, total_usage)` — sempre desempacotar; `token_usage` acumulado por chunk no status.json (sobrevive a resume)
- **Cleanup timer (1h)**: re-enfileira PENDING órfãos > 5min E PROCESSING sem progresso > 1h (mede por `lease_renewed_at`, fallback `created_at`; máx 3 retomadas via `resume_attempts`, depois ERROR)
- **host.json queues**: `messageEncoding: "none"` (obrigatório — extension bundle v4 default é Base64, incompatível com SDK Python)
- **Consolidação preenche NaN** com `"Não Identificado"` (N1-N4)
- **Remove colunas de classificação do chunk original** antes do merge → evita `N1.1`, `N2.1`
- **fillna de `status`** é condicional (`if "status" in final_df.columns`) — só caminho legado
- **CancelJob**: escreve `CANCELLED` no `status.json`. `process_single_job()` verifica status entre batches de chunks
- **status.json com file lock** — operações atômicas via `locked_status()` context manager. Nunca ler+escrever status.json sem lock
- **Excel base64 em arquivo separado** — `ApproveClassifications` salva em `approved_result_b64.txt`, não no `status.json`

### Projetos e Setores
- **`resolve_hierarchy()`** busca: (1) hierarquia própria → `"own"`, (2) sem → `"padrao"`. Não existe `"inherited"`
- **Setor não tem hierarquia** — só KB
- **`delete_sector(force=False)`** levanta `ValueError` se há projetos. `force=True` deleta projetos primeiro
- **Compatibilidade legada**: `varejo` e `educacional` usam ML via `use_legacy_ml=True`

### Excels
- **Download classificação** (DownloadJobExcel): [ID col se existir], Descricao, N1-N4, Fonte. Sem Confiança
- **Final revisão** (ApproveClassifications): [ID col se existir], Descrição, N1-N4, Fonte. Itens editados → "Ajuste Manual"
- **Intermediário** (consolidate_job): sem `status`/`matched_terms`; source com label amigável
- **`friendly_source_label()`** em `utils.py`: `"KB (Direct Match)"` → `"Base de Aprendizado"`, `"LLM (Batch)"` → `"Grok"`, `"consultant_correction"` → `"Ajuste Manual"`

### Analytics
- **`generate_analytics()`**: retorna apenas Pareto (N1-N4). `gaps`/`ambiguity` retornam `[]` (compat)
- **`generate_summary()`**: unico/nenhum derivados de N1-N4. `ambiguo` sempre 0 no LLM-direto
