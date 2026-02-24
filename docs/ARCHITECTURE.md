# Arquitetura — Spend Analysis v3

## Visão Geral

O v3 resolve três problemas estruturais do v2:

1. **Sem loop de aprendizado**: correções manuais nunca voltavam para o pipeline. Agora a KB alimenta o próximo job via few-shot RAG.
2. **Modelo de dados limitado**: "setor" misturava vertical de mercado com cliente. Agora: Setor (vertical) → Projeto (empresa/escopo).
3. **God file**: `function_app.py` com ~1800 linhas. Agora: entry point de ~33 linhas + 7 Blueprints.

---

## Componentes

### Backend

```
function_app.py          ← entry point: cria FunctionApp + registra blueprints
    │
    ├── blueprints/projects_bp.py        CRUD setores e projetos
    ├── blueprints/classification_bp.py  SubmitJob, GetStatus, GetJobResults
    ├── blueprints/review_bp.py          ReclassifyItems, ApproveClassifications
    ├── blueprints/knowledge_bp.py       KB CRUD (projeto + setor), versões, cobertura, import/export, promote (19 endpoints)
    ├── blueprints/models_bp.py          ML legacy: TrainModel, GetModelHistory, etc.
    ├── blueprints/copilot_bp.py         Copilot Studio: get-token, SearchMemory
    └── blueprints/worker_bp.py          Timer 15s → run_worker_cycle()
           │
           └── src/worker_helpers.py     Lógica do worker (cleanup, get_active, process, consolidate)
                   │
                   └── src/core_classification.py   Pipeline de classificação por chunk
                           │
                           ├── [novo] LLM direto + few-shot da KB
                           │       └── src/kb_retriever.py    TF-IDF cosine similarity
                           │       └── src/llm_classifier.py  Grok/xAI async
                           │       └── src/hierarchy_validator.py  Validação pós-LLM
                           │
                           └── [legado] ML + Dicionário + LLM fallback
                                   └── src/hybrid_classifier.py
                                   └── src/taxonomy_engine.py
                                   └── src/ml_classifier.py
```

### Frontend

```
pages/taxonomy.tsx          Página principal + state machine
    │
    ├── CollapsibleSidebar (layout/)   ← sidebar navy colapsável com pinned state
    │    ├── Logo (branding)
    │    ├── ProjectSelect variant="dark"
    │    └── SessionSidebar               ← lista de sessões + footer (sem container próprio)
    │
    ├── ContextBar (layout/)               ← breadcrumb + step indicator + KB button
    │
    ├── KnowledgeSlideOver (taxonomy/)     ← slide-over com 2 abas: KnowledgeTab + SectorKnowledgeTab
    │
    ├── hooks/useTaxonomySession.ts   Lifecycle de sessão (project-aware, review states)
    ├── hooks/useProjects.ts          CRUD projetos + sync IndexedDB/backend
    ├── hooks/useReview.ts            State machine de revisão (Map de estados por item)
    ├── hooks/useHierarchy.ts         Parse hierarquia → tree para cascading dropdowns
    ├── hooks/useVirtualScroll.ts     Windowing para 50K rows (height fixo 52px)
    └── hooks/useCopilot.ts           Copilot Studio (gated por reviewCompleted)
```

#### Paleta Visual

| Elemento | Valor |
|----------|-------|
| Sidebar bg | `gradient from-[#1c0957] via-[#180847] to-[#120535]` |
| Accent principal | `#0693e3` / `accent-500` (tabs ativas, botões) |
| Accent brilhante | `#38a8f5` / `accent-400` (hover, highlights) |
| Gradiente signature | `from-[#0693e3] to-[#9b51e0]` (CTA principal) |
| AI/Copilot | `#9b51e0` / `ai-400` |
| Success | `#2db17f` / `mint-500` |
| Separadores | `border-white/10` |
| Design tokens | `frontend/src/lib/design-tokens.ts` (source of truth) |

---

## Pipeline de Classificação

### Fluxo Completo

```
1. SubmitTaxonomyJob (POST)
   ├── Lê arquivo CSV/XLSX
   ├── Ordena por descrição (case-insensitive) ← agrupa similares no batch LLM
   ├── Divide em chunks de 500 linhas
   ├── Salva chunks como chunk_0.json, chunk_1.json, ...
   └── Cria status.json com status=PENDING

2. ProcessTaxonomyWorker (timer 15s)
   ├── cleanup_stale_jobs() ← jobs PROCESSING > 1h → ERROR
   ├── get_active_jobs() ← carrega project_config + resolve_hierarchy + KB
   ├── Round-robin: max 5 chunks simultâneos entre todos os jobs ativos
   │   └── process_single_chunk()
   │           ├── Carrega chunk_X.json
   │           ├── core_classification.process_dataframe_chunk()
   │           │       [novo] Two-Phase Classification:
   │           │         Phase 1: KB direct match (sim ≥ 0.90) → classificação sem LLM
   │           │         Phase 2: LLM com enriched examples (matches parciais do batch)
   │           │       [legado] hybrid_classifier → llm fallback
   │           │       hierarchy_validator.validate_and_correct()
   │           └── Salva result_X.json
   └── consolidate_job() quando todos os chunks processados
           ├── Merge chunk_X.json + result_X.json (original + classificação)
           ├── Remove colunas de classificação do chunk original (evita N1.1, N2.1)
           ├── Preenche NaN com "Não Identificado" (N1-N4)
           ├── Source com label amigável via friendly_source_label()
           └── status → CLASSIFIED

3. Revisão humana (frontend ReviewTab)
   ├── GetJobResults → carrega items classificados
   ├── useReview state machine: approved / edited / rejected per item
   ├── ReclassifyItems → re-classifica rejeitados com instrução do consultor
   └── ApproveClassifications
           ├── Salva decisões do consultor
           ├── Alimenta KB (source: llm_approved / consultant_correction / reclassified_with_guidance)
           ├── Gera Excel final (base64)
           └── status → COMPLETED

4. Copilot desbloqueado (useCopilot.ts)
   ├── Análise conversacional dos dados aprovados
   └── smart-context/ RAG client-side
```

### Dois Caminhos de Classificação

**Caminho Novo — Two-Phase Classification (projetos com KB)**
```python
# core_classification._llm_direct_pipeline()

# PHASE 1: KB Direct Match (sem LLM)
# Para cada item, busca match na KB mesclada (setor + projeto)
# Se similaridade >= 0.90 e classificação completa → usa KB direto
# Resultado: "KB (Direct Match)" / "Base de Aprendizado"

# PHASE 2: LLM com Enriched Examples
# Itens restantes vão ao Grok com exemplos enriched:
1. KBRetriever.select_enriched_examples(kb_entries, descriptions, max_per_n4=3)
   → Seleciona matches parciais (sim >= 0.30) relevantes ao batch (não globais)
   → Limita 3 por N4 para garantir diversidade
2. classify_items_with_llm(few_shot_examples=enriched_examples, client_context=...)
   → System message: hierarquia customizada + exemplos confirmados + instrução
3. hierarchy_validator.validate_and_correct()
   → Cascata: exact → level_shift → partial_fuzzy → n4_reverse → no_match

# Thresholds:
# KB_DIRECT_MATCH_THRESHOLD = 0.90
# KB_ENRICHED_EXAMPLE_MIN_SIM = 0.30
# KB_ENRICHED_MAX_EXAMPLES = 20
```

**Caminho Legado (setores com modelo ML treinado)**
```python
# core_classification._legacy_ml_pipeline()
1. ML (TF-IDF + LogisticRegression)
   → confidence >= 0.45: "Unico" (usa ML)
   → confidence 0.25-0.44: "Ambiguo" (tenta dicionário)
   → confidence < 0.25: fallback dicionário
2. Dicionário (regex/keywords do Spend_Taxonomy.xlsx)
3. LLM fallback para itens "Nenhum"
4. hierarchy_validator (se custom_hierarchy presente)
```

---

## Knowledge Base (KB)

### Estrutura por Projeto + Setor

```
models/projects/{project_id}/
├── knowledge_base.json      ← array de KBEntry (dedup por description_norm apenas)
└── kb_versions/

models/sectors/{sector_name}/
├── sector_config.json
├── knowledge_base.json      ← KB curada do setor (promovida de projetos ou editada diretamente)
└── kb_versions/
```

### Ciclo de Vida de uma Entrada KB

```
Consultor aprova item classificado → source: "llm_approved"
Consultor edita e aprova          → source: "consultant_correction"
Consultor rejeita + instrução     → re-classifica → aprova → source: "reclassified_with_guidance"
```

### Few-Shot RAG (KBRetriever)

```python
KBRetriever(kb_entries)
  # TF-IDF (1,2)-grams sobre description_norm
  # Criado 1x por job com KB mesclada (setor + projeto) — não recriar por chunk

  # Método principal (Two-Phase):
  .select_enriched_examples(kb_entries, descriptions, max_per_n4=3, max_examples=20)
  # Seleciona matches parciais (sim >= 0.30) relevantes ao batch específico
  # Limita 3 por N4 para diversidade

  # Método fallback (se enriched vazio):
  .select_representative_examples(max_k=10)
  # Greedy coverage: maximiza N4s distintos cobertos

# Inserido no system message do LLM:
"EXEMPLOS CONFIRMADOS PELO CONSULTOR (use como referência):
- "Válvula esfera DN50" → N1: Materiais, N2: Tubulação, N3: Válvulas, N4: Válvulas de Esfera
- ..."
```

### Toggle use_sector_kb

Cada projeto tem `use_sector_kb` (default true) em `project_config.json`. Quando false:
- Worker não carrega KB do setor para merge
- Reclassificação não inclui KB do setor
- Coverage não contabiliza entradas do setor
- Frontend: KnowledgeTab não mostra entradas do setor, sem botão "Promover"
- Frontend: aba "Setor" no SlideOver mostra empty state

KB do setor é SEMPRE acessível via SectorKnowledgeTab para gestão direta, independente do toggle.

### Labels de Fonte (friendly_source_label)

| Source interno | Label amigável |
|----------------|---------------|
| `KB (Direct Match)` | Base de Aprendizado |
| `LLM (Batch)` | Grok |
| `LLM (Reclassified)` | Grok |
| `Taxonomy (Dict)` | Dicionário |
| `ML` | ML |

Usados nos Excels (intermediário e final) e no badge da coluna FONTE na `ReviewTable`.

### Colunas dos Excels

- **Excel final** (ApproveClassifications): Descricao, N1-N4, Fonte (label amigável). Sem Confianca nem Status Revisao.
- **Excel intermediário** (consolidate_job): Descricao, N1-N4, Fonte (label amigável). Sem `status` nem `matched_terms` no caminho LLM-direto.

---

## Gestão de Projetos

### Resolução de Hierarquia

```python
resolve_hierarchy(project_id, models_dir)
  → (hierarchy_list, source)

Prioridade:
  1. custom_hierarchy do projeto → source = "own"
  2. custom_hierarchy do setor   → source = "inherited"
  3. None                        → source = "padrao" (usa Spend_Taxonomy.xlsx)
```

### project_id Gerado

```python
_slugify(sector + "-" + display_name)
# "naval" + "WÄRTSILÄ S.A." → "naval-wartsila-s-a"
```

---

## Hierarquia Customizada

Problema específico que influencia várias decisões:

**N4s duplicados**: "Materiais OEM" aparece sob 18 marcas diferentes (WARTSILA, MAN, CATERPILLAR, etc.). Se a hierarquia fosse um dict keyed por N4, perderia 17 entradas.

**Solução**: hierarquia como lista de dicts:
```python
[
  {"N1": "Materiais", "N2": "OEM WARTSILA", "N3": "Peças de Motor", "N4": "Materiais OEM"},
  {"N1": "Materiais", "N2": "OEM MAN",     "N3": "Peças de Motor", "N4": "Materiais OEM"},
  # ... mais 16 marcas
]
```

`_format_hierarchy_compact()` em `llm_classifier.py` aceita lista ou dict (backward compat).

---

## Validador de Hierarquia (hierarchy_validator.py)

Pós-processamento que corrige erros do LLM. Cascata aplicada em sequência:

```
A. Exact path match (N1,N2,N3,N4) case-insensitive → mantém
B. Level shift: N1 retornado é N2 válido → shift +1 nível
C. Partial path + fuzzy match scoped (N3/N4 dentro do branch correto)
D. N4-based reverse lookup: pontua por overlap com N1/N2/N3
E. No match → zera para "Não Identificado" + status "Nenhum"
```

`HierarchyLookup` é pré-construído 1x por job em `get_active_jobs()`. Não reconstruir por chunk.

---

## Worker Round-Robin

```python
# worker_helpers.get_active_jobs()
active_jobs = [job1, job2, job3]  # jobs com status PROCESSING

# Round-robin: 1 chunk por job por rodada
chunks_to_process = [
    job1.next_chunk,
    job2.next_chunk,
    job3.next_chunk,
][:MAX_PARALLEL_CHUNKS]  # max 5

# Processamento paralelo
with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CHUNKS) as executor:
    futures = [executor.submit(process_single_chunk, chunk) for chunk in chunks_to_process]
```

Garante que jobs pequenos não ficam bloqueados por jobs grandes.

---

## Frontend — State Machine

### Estados da Sessão

```typescript
type SessionPhase =
  | 'idle'          // sem sessão ativa
  | 'uploading'     // upload em andamento
  | 'processing'    // job em PROCESSING
  | 'classified'    // job em CLASSIFIED (revisão disponível)
  | 'reviewing'     // revisor abriu a aba de revisão
  | 'completed'     // ApproveClassifications chamado, status COMPLETED
```

### Transições

```
idle → uploading (upload de arquivo)
uploading → processing (SubmitTaxonomyJob retorna jobId)
processing → classified (polling detecta status=CLASSIFIED)
classified → reviewing (usuário clica na aba Revisar)
reviewing → completed (finalizeReview → ApproveClassifications)
```

### Tabs por Fase

| Fase | Classificar | Revisar | Conhecimento | Analisar |
|------|-------------|---------|--------------|---------|
| idle | Ativo | Locked | Ativo | Locked |
| uploading/processing | Disabled | Locked | Locked | Locked |
| classified | Ativo | **Ativo** | Ativo | Locked |
| reviewing | Ativo | Ativo | Ativo | Locked |
| completed | Ativo | Ativo | Ativo | **Ativo** |

---

## IndexedDB Schema v2

```typescript
// DB_VERSION = 2
// Migration: v1 → v2 adiciona reviewState: 'completed' em sessões existentes

stores: {
  sessions: {
    keyPath: 'sessionId',
    indexes: ['by-timestamp', 'by-project'],
    // Novos campos v3: reviewState, reviewedItems, approvedSummary, projectId
  },
  projects: {           // NOVO
    keyPath: 'id',
    indexes: ['by-sector', 'by-name'],
  },
  reviewProgress: {     // NOVO — persistência parcial da revisão
    keyPath: 'sessionId',
    // Armazena Map<number, ReviewItemState> serializado
    // Auto-save a cada 5s em useReview.ts
  }
}
```

---

## Decisões Técnicas

| Decisão | Alternativas Consideradas | Razão Escolhida |
|---------|--------------------------|-----------------|
| Few-shot com TF-IDF | Embeddings semânticos (OpenAI, sentence-transformers) | scikit-learn já é dependência; sem custo extra; latência mínima |
| KB como JSON filesystem | PostgreSQL, Azure Table Storage | Sem infra adicional; compatível com File Share existente; snapshots triviais |
| Revisão no frontend (não backend) | Backend state machine | UX mais fluida; auto-save IndexedDB; sem round-trips para cada clique |
| Virtual scroll (52px fixo) | react-virtual, tanstack-virtual | Zero dependências extras; implementação simples suficiente para 50K rows |
| Hierarquia como lista | Dict keyed por N4 | Suporta N4s duplicados (ex: "Materiais OEM" em 18 marcas) |
| Status CLASSIFIED (intermediário) | Ir direto para COMPLETED | Força o loop de revisão humana antes do download |
| Sidebar unificado em `aside` (taxonomy.tsx) | SessionSidebar com container próprio | Elimina conflito visual branco/navy; `SessionSidebar` fica sem responsabilidade de layout |
| Slug de setor auto-gerado | Campo manual digitado pela usuária | Usuárias não são técnicas; `normalize('NFD')` garante suporte a acentos e caracteres especiais |
| ProjectSelect com prop `variant` | Componente separado para sidebar | Mesmo componente, dois contextos; evita duplicação de lógica de agrupamento |
| KB do setor com CRUD completo | KB do setor read-only + promote-only | Consultor precisa curar KB do setor (editar, deletar entradas erradas); 9 endpoints espelham os de projeto |
| Toggle `use_sector_kb` por projeto | Merge sempre habilitado | Projetos podem precisar de KB isolada (ex: setor novo com KB vazia que atrapalha) |
| Design tokens centralizados | Cores hardcoded nos componentes | `design-tokens.ts` como source of truth; `tw.*` classes compostas evitam repetição |
| CollapsibleSidebar como componente | Sidebar inline em taxonomy.tsx | Separação de responsabilidades; sidebar colapsável melhora uso do espaço |
