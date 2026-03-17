# Relatório de Prontidão para Produção

**Sistema:** Spend Analysis v3
**Data:** 2026-03-17
**Escopo:** Sistema completo (backend + frontend + integrações)
**Fases executadas:** 1-5 (Feature Discovery, Arquitetura, Concorrência, Caos, Segurança)

---

## Veredito Geral

| Dimensão | Nota (1-10) | Status |
|----------|------------|--------|
| Arquitetura | 6 | 🟡 |
| Concorrência | 4 | 🔴 |
| Resiliência | 5 | 🟡 |
| Segurança | 2 | 🔴 |
| **Prontidão Geral** | **4.3** | **🔴** |

**Recomendação:** **NÃO PRONTO** para produção aberta. Pronto para uso interno controlado (< 10 usuários, single-instance) **com ressalvas**. Precisa de autenticação, CORS restrito, e correções de concorrência antes de expor publicamente.

---

## Resumo Executivo

O Spend Analysis v3 é uma plataforma funcional e bem desenhada para seu domínio: classificação de gastos corporativos com loop de aprendizado humano. O pipeline Two-Phase (KB direct match + LLM), o design de chunks resumíveis, e o sistema de poison queue + cleanup timer demonstram maturidade técnica no happy path.

No entanto, a avaliação identificou **lacunas estruturais** que impedem uso em produção aberta:

1. **Zero autenticação**: 47 endpoints acessíveis por qualquer pessoa com a URL. Tokens LLM ($0.05+/job) podem ser consumidos sem restrição. Dados corporativos (gastos, fornecedores) ficam expostos.

2. **Concorrência frágil**: O mecanismo de file locking (`filelock.FileLock`) protege contra concorrência intra-processo, mas **não funciona entre instâncias** do Azure Functions. Se o sistema escalar (comportamento padrão do Consumption Plan), dados da Knowledge Base podem ser corrompidos silenciosamente.

3. **Degradação silenciosa**: Quando a API Grok/xAI falha, o sistema marca o job como CLASSIFIED (não ERROR), preenchendo 100% dos itens com "Não Identificado". Consultores recebem resultados inúteis sem aviso claro.

4. **Operações não-atômicas**: 5 de 9 operações críticas não são idempotentes. `ApproveClassifications` modifica a KB antes de verificar o status atomicamente, criando risco de entries órfãs. `rollback_to_version()` tem janela de perda de dados documentada.

Para uso interno com 5-10 consultores, o sistema funciona adequadamente desde que limitado a uma única instância (`WEBSITE_MAX_DYNAMIC_APPLICATION_SCALE_OUT=1`) e com CORS restrito ao domínio do frontend.

---

## Findings Críticos (ação imediata)

| # | Categoria | Problema | Impacto | Correção | Esforço |
|---|----------|---------|---------|---------|---------|
| 1 | Segurança | 47 endpoints `AuthLevel.ANONYMOUS` | Qualquer pessoa acessa/modifica dados e consome tokens LLM | `AuthLevel.FUNCTION` + function keys | Baixo |
| 2 | Segurança | CORS `"*"` em `host.json:24-27` | CSRF, requests de qualquer origem | Restringir ao domínio do frontend | Mínimo |
| 3 | Concorrência | FileLock não funciona cross-instance | KB data loss silenciosa em multi-instância | Forçar `maxInstances=1` no Azure (curto prazo) | Mínimo |
| 4 | Resiliência | Fallback LLM silencioso — job CLASSIFIED com 0% classificação útil | Consultores recebem resultados inúteis sem aviso | Adicionar `fallback_pct` ao status.json; alertar se > 50% | Baixo |
| 5 | Concorrência | `rollback_to_version()` não-atômico — `self.entries =` fora do lock | Perda silenciosa de KB entries em rollback concorrente | Mover operação para dentro do `_kb_lock` | Baixo |
| 6 | Concorrência | `project_config.json` e `sector_config.json` sem file lock | Updates concorrentes perdem dados | Adicionar FileLock (mesmo padrão de `_kb_lock`) | Baixo |

## Findings Importantes (próximo sprint)

| # | Categoria | Problema | Impacto | Correção | Esforço |
|---|----------|---------|---------|---------|---------|
| 7 | Concorrência | `ApproveClassifications` modifica KB antes de status check atômico | KB entries órfãs se status mudou | Reordenar: status check → KB update | Médio |
| 8 | Concorrência | `ProcessTaxonomyJob` PENDING→PROCESSING sem check-and-set atômico | Processamento duplicado do mesmo job | Usar `locked_status()` com check | Baixo |
| 9 | Resiliência | Retry LLM sem jitter — thundering herd com 15 threads | Rate limiting (429) sustentado | Adicionar `random.uniform(0, 1)` ao backoff | Mínimo |
| 10 | Resiliência | `map_categories_with_llm()` sem `_LLM_SEMAPHORE` | Excede rate limit quando paralelo com classificação | Usar `_LLM_SEMAPHORE` | Baixo |
| 11 | Resiliência | `enqueue_job()` falha silenciosa sem feedback | Job PENDING nunca processado, usuário não sabe | Retornar bool + warning no response 202 | Baixo |
| 12 | Resiliência | Health check não testa API Grok | Indisponibilidade não detectada proativamente | Adicionar probe LLM mínima com cache 5min | Baixo |
| 13 | Arquitetura | Sem observabilidade estruturada | Sem métricas P95, taxa de erros, consumo de tokens | Azure Application Insights + custom metrics | Médio |
| 14 | Arquitetura | Sem política de retenção de jobs | `taxonomy_jobs/` cresce indefinidamente (10-50MB/job) | Timer para deletar jobs > 30 dias COMPLETED/ERROR | Médio |
| 15 | Segurança | Sem rate limiting nos endpoints | Abuso de tokens LLM, DoS | Rate limit por IP (max 5 jobs/hora) | Médio |

## Findings Menores (backlog)

| # | Categoria | Problema | Impacto | Correção | Esforço |
|---|----------|---------|---------|---------|---------|
| 16 | Arquitetura | Dead code: `taxonomy_mapper.py` (177 linhas) | Complexidade cognitiva | Remover arquivo | Mínimo |
| 17 | Arquitetura | `run_worker_cycle()` + `get_active_jobs()` DEPRECATED (130+ linhas) | Confusão em manutenção | Remover funções | Mínimo |
| 18 | Resiliência | Consolidação sem indicação de progresso | UX — "processando" por minutos sem feedback | Adicionar status intermediário "CONSOLIDATING" | Baixo |
| 19 | Resiliência | Sem limite de tamanho de upload | OOM em jobs > 20k linhas | Rejeitar uploads > 50MB ou > 20k linhas | Baixo |
| 20 | Resiliência | Direct Line API sem retry | Copilot falha em timeout | 1 retry com timeout 5s | Baixo |
| 21 | Arquitetura | Python local 3.12 vs Azure 3.13 | Incompatibilidades sutis | Alinhar versões | Baixo |
| 22 | Concorrência | `update_job_progress` pode pular valores de progresso | Progresso visual irregular no frontend | Cosmético — valor final correto | Mínimo |
| 23 | Arquitetura | `MemoryEngine` path fixo sem file lock | Race condition em Copilot memory | Usar `get_models_dir()` + filelock | Baixo |
| 24 | Concorrência | `SubmitTaxonomyJob` sem idempotency key | Submissão duplicada cria jobs duplicados | Hash de conteúdo como chave de dedup | Médio |

---

## Métricas por Fase

### Fase 1 — Feature Discovery
- Arquivos mapeados: 92 (Python + TypeScript)
- Linhas de código: 28.295 (backend 8.191 + frontend 14.169 + testes 5.935)
- Fluxos de dados: 4 (classificação, revisão, promoção KB, cleanup)
- Pontos de integração: 5 (Grok API, Azure File Share, Storage Queue, Direct Line, IndexedDB)
- Endpoints HTTP: 47 + 3 triggers
- Regras de negócio: 16
- Itens de dívida técnica: 18

### Fase 2 — Arquitetura
- Problemas encontrados: 11 (3 críticos, 4 altos, 4 médios)
- SPOFs identificados: 4 (Grok API, File Share, Storage Queue, single instance)
- Padrões inadequados: 3 (file-based storage, sem auth, sem provider abstraction)

### Fase 3 — Concorrência
- Pontos de escrita: 14
- Race conditions: 8 (3 críticas, 3 altas, 2 médias)
- Operações não-idempotentes: 5 de 9
- Cenários de deadlock: 1 (mitigado por timeout 10s)
- Quick wins identificados: 5 (~5h de implementação)

### Fase 4 — Resiliência
- Cenários de desastre: 11 (3 críticos, 4 altos, 4 médios)
- Componentes sem timeout adequado: 2 de 6 (map_categories_with_llm, enqueue_job)
- Componentes sem retry: 3 de 6 (File Share, enqueue_job, Direct Line)
- Componentes sem circuit breaker: 6 de 6
- MTTR estimado: 30-60min (detecção manual)

### Fase 5 — Segurança
- Endpoints sem autenticação: 47 de 47
- CORS wildcard: Sim
- Rate limiting: Nenhum
- Validação de input (upload size): Nenhuma
- RBAC: Nenhum

---

## Plano de Ação

### Semana 1 (Quick Wins — ~2 dias)
- [ ] CORS: restringir `"*"` para domínio real do frontend (`host.json:25`)
- [ ] Auth: migrar para `AuthLevel.FUNCTION` com function keys (`function_app.py:14`)
- [ ] Scale: configurar `WEBSITE_MAX_DYNAMIC_APPLICATION_SCALE_OUT=1` no Azure
- [ ] Rollback atômico: mover `self.entries = snapshot` para dentro do `_kb_lock` (`knowledge_base.py:275-286`)
- [ ] FileLock em configs: adicionar lock em `update_project()` e `update_sector()` (`project_manager.py`)
- [ ] Jitter no retry LLM: `time.sleep(2**attempt + random.uniform(0, 1))` (`llm_classifier.py:418`)
- [ ] Semáforo em `map_categories_with_llm()` (`llm_classifier.py:600-637`)

### Semana 2-4 (Correções Estruturais — ~5 dias)
- [ ] Fallback detection: contar itens com `confidence == 0.0` após classificação; adicionar `fallback_pct` ao status.json (`worker_helpers.py:654`)
- [ ] Check-and-set atômico: PENDING→PROCESSING via `locked_status()` (`worker_helpers.py:608-618`)
- [ ] Reordenar ApproveClassifications: status check antes de KB update (`review_bp.py:177-283`)
- [ ] `enqueue_job()` retornar bool + warning no response (`queue_helpers.py`, `classification_bp.py`)
- [ ] Health check com probe Grok (1 item, timeout 5s, cache 5min) (`health_bp.py`)
- [ ] Política de retenção: timer para deletar jobs > 30 dias (`worker_bp.py`)
- [ ] Remover dead code: `taxonomy_mapper.py`, `run_worker_cycle()`, `get_active_jobs()`
- [ ] Limite de upload: rejeitar > 50MB ou > 20.000 linhas (`classification_bp.py`)

### Mês 2+ (Hardening para Escala)
- [ ] Observabilidade: Azure Application Insights + custom metrics (llm_latency, kb_hit_rate, tokens_consumed)
- [ ] Rate limiting: max 5 jobs/hora por usuário/IP
- [ ] Circuit breaker para API Grok (after N consecutive failures, skip LLM for 30s)
- [ ] Idempotency key para SubmitTaxonomyJob (hash conteúdo + projectId)
- [ ] Abstração de provider LLM: interface `LLMProvider` com fallback para provider secundário
- [ ] Migrar storage para Azure Cosmos DB ou Blob Storage com ETags (elimina FileLock)
- [ ] RBAC: Azure AD B2C com roles (consultor, admin, viewer)

---

## Apêndices

### Pontos Positivos Destacados
O sistema tem vários padrões bem implementados que devem ser preservados:

1. **Chunks resumíveis** — `find_next_chunks()` verifica `result_X.json` existente, tornando o processamento naturalmente tolerante a interrupções
2. **Poison queue + cleanup timer** — safety net dupla para jobs que falham
3. **Two-Phase classification** — KB direct match (≥0.90) economiza chamadas LLM
4. **KB dedup por `description_norm`** — simples e eficaz para o domínio
5. **Hierarchy validation cascade** — 4 estratégias de correção (exact → shift → fuzzy → n4-reverse)
6. **Excel b64 em arquivo separado** — evita status.json de 10-15MB
7. **Source authority ranking** — `consultant_correction(2) > reclassified(1) > llm_approved(0)`
8. **Cancellation check entre batches** — processamento para graciosamente

### Configuração Recomendada para Azure (Imediata)
```
WEBSITE_MAX_DYNAMIC_APPLICATION_SCALE_OUT=1
FUNCTIONS_WORKER_PROCESS_COUNT=1
```
Isso garante que apenas uma instância processe jobs, neutralizando os problemas de FileLock cross-instance.
