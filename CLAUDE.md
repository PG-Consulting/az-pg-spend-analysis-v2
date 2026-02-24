# CLAUDE.md — Spend Analysis v3 (new-solution)

## Visão Geral do Projeto

Plataforma de classificação de gastos corporativos com **loop de aprendizado humano**. Consultores revisam as classificações antes da entrega, e suas correções alimentam uma **Knowledge Base (KB)** por projeto. A KB do projeto é automaticamente mesclada com a **KB do setor** (referência viva — sem cópia) e usada como few-shot RAG nas classificações futuras, melhorando progressivamente a acurácia do LLM. Consultores podem promover seletivamente entradas do projeto para o setor, criando uma base curada compartilhada entre projetos.

**Domínio**: Spend Analysis / Procurement / Classificação taxonômica N1-N4
**Cliente**: PG Consultoria — AI Team
**Diretório backup (v2)**: `../az-pg-spend-analysis-v2` (NÃO alterar)

---

## Diferenças em Relação ao v2

| Aspecto | v2 | v3 (new-solution) |
|---------|----|--------------------|
| Organização | Setor (texto livre) | Setor + Projeto (hierarquia) |
| Knowledge Base | `memory_engine.py` (isolado) | `KnowledgeBase` por setor + projeto (merge automático, few-shot RAG) |
| Revisão humana | Inexistente | Aba "Revisar" obrigatória antes do download |
| Entry point | `function_app.py` (~1800 linhas) | `function_app.py` (~33 linhas) + 7 Blueprints |
| Status do job | `CLASSIFIED → COMPLETED` | `CLASSIFIED → revisão → APPROVED → COMPLETED` |
| Copilot | Disponível imediatamente | Bloqueado até revisão completa |

---

## Arquitetura

### Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | Azure Functions v2 (Python 3.9+) com Blueprints |
| Frontend | Next.js 14 + TypeScript + React 18 + TailwindCSS 3.4 |
| ML | scikit-learn (TF-IDF + Logistic Regression) — caminho legado |
| LLM | Grok/xAI API (`grok-4-1-fast-reasoning`) |
| Few-shot RAG | TF-IDF cosine similarity (`KBRetriever`) |
| Chat | Microsoft Copilot Studio (Direct Line API) |
| Storage | Azure File Share (`/mount/models`) / IndexedDB (client) |
| CI/CD | GitHub Actions → Azure Static Web Apps |

### Pipeline de Classificação

```
Upload de arquivo
  → Ordenar por descrição (agrupa similares no mesmo batch LLM)
  → Dividir em chunks de 500 linhas
  → Fila de jobs filesystem (taxonomy_jobs/)

Worker (timer 15s, round-robin):
  → Carrega KB do setor (se use_sector_kb=true) + KB do projeto → merge (1x por job)
  → Cria KBRetriever indexado com KB mesclada
  → Para cada chunk (Two-Phase Classification):
       FASE 1: KB Direct Match (sim ≥ 0.90)
         → Itens com match direto na KB: classificação instantânea (sem LLM)
       FASE 2: LLM com Enriched Examples
         → Itens restantes: coleta matches parciais como exemplos enriched
         → Envia ao LLM com exemplos relevantes ao batch (não globais)
       [Legado] ML → Dicionário → LLM fallback (setores com modelo treinado)
  → Validação de hierarquia (cascade: exact → shift → fuzzy → n4-reverse)
  → Consolida → preenche vazios com "Não Identificado"
  → Status: CLASSIFIED (aguarda revisão humana)

Revisão humana (frontend):
  → Consultor aprova / edita / rejeita itens
  → Itens rejeitados → re-classificação com instrução
  → ApproveClassifications → alimenta KB do projeto → gera Excel → COMPLETED
  → Consultor pode promover entradas do projeto → KB do setor (ação separada)

Copilot desbloqueado após COMPLETED
```

### Lifecycle de Jobs

```
PENDING → PROCESSING → CLASSIFIED → APPROVED → COMPLETED
                            ↑                       ↑
                     worker para aqui    ApproveClassifications
```

Auto-limpeza: jobs `PROCESSING` há mais de 1 hora → `ERROR`.

---

## Estrutura do Projeto

```
new-solution/
├── function_app.py              # Entry point enxuto (~33 linhas) — registra blueprints
├── host.json                    # Config Azure Functions (timeout 30min)
├── requirements.txt             # Dependências Python
├── local.settings.json          # Secrets locais (NÃO commitar)
├── local.settings.json.example  # Template sem secrets
├── staticwebapp.config.json     # Config routing SWA
│
├── blueprints/
│   ├── projects_bp.py           # CRUD setores + projetos (9 endpoints, incl. DeleteSector)
│   ├── classification_bp.py     # SubmitJob, GetStatus, GetJobResults (3 endpoints)
│   ├── review_bp.py             # ReclassifyItems, ApproveClassifications (2 endpoints)
│   ├── knowledge_bp.py          # KB projeto + setor: CRUD, coverage, versões, import/export, promote (19 endpoints)
│   ├── models_bp.py             # Treinamento ML legacy (6 endpoints)
│   ├── copilot_bp.py            # Copilot Studio legacy (3 endpoints)
│   └── worker_bp.py             # ProcessTaxonomyWorker — timer 15s
│
├── src/
│   ├── utils.py                 # get_models_dir(), safe_json_dumps(), constantes de dirs
│   ├── project_manager.py       # CRUD setores/projetos, resolve_hierarchy()
│   ├── knowledge_base.py        # KnowledgeBase class (projeto + setor): CRUD, versões, cobertura, merge, promote
│   ├── kb_retriever.py          # KBRetriever: TF-IDF cosine similarity para few-shot
│   ├── core_classification.py   # Pipeline: LLM direto (novo) ou ML+Dict+LLM (legado)
│   ├── worker_helpers.py        # Fila de jobs: cleanup, get_active, process_chunk, consolidate
│   ├── llm_classifier.py        # Integração Grok/xAI (async, 20 workers) + few-shot + instrução
│   ├── hierarchy_validator.py   # Validação cascata pós-LLM contra hierarquia customizada
│   ├── preprocessing.py         # normalize_text(), build_tfidf_vectorizer()
│   ├── taxonomy_engine.py       # Classificação por dicionário (regex/keywords) + analytics
│   ├── ml_classifier.py         # Preditor ML (TF-IDF + LogisticRegression)
│   ├── model_trainer.py         # Pipeline de treinamento com versionamento
│   └── taxonomy_mapper.py       # Mapeamento de hierarquia customizada (legado)
│
├── models/
│   ├── sectors/                 # Configs de setores + KBs de setor
│   │   └── {sector_name}/
│   │       ├── sector_config.json
│   │       ├── knowledge_base.json  # KB curada do setor (promovida de projetos)
│   │       └── kb_versions/     # Snapshots para rollback
│   ├── projects/                # Configs de projetos + KBs
│   │   └── {project_id}/
│   │       ├── project_config.json
│   │       ├── knowledge_base.json
│   │       └── kb_versions/     # Snapshots para rollback
│   ├── taxonomy_jobs/           # Fila de jobs async
│   ├── varejo/                  # ML model legado
│   └── educacional/             # ML model legado
│
├── data/taxonomy/
│   └── Spend_Taxonomy.xlsx      # Dicionário master de classificação
│
├── tests/                       # Testes backend (pytest)
│   ├── __init__.py
│   ├── conftest.py              # Fixtures compartilhadas (tmp_models_dir, sample_hierarchy, etc.)
│   ├── test_preprocessing.py    # 18 testes — normalize_text, corpus, TF-IDF
│   ├── test_hierarchy_validator.py # 25 testes — HierarchyLookup, validate_and_correct cascade
│   ├── test_kb_retriever.py     # 18 testes — retrieve, batch, representative, enriched selection
│   ├── test_knowledge_base.py   # 41 testes — CRUD, dedup, versioning, coverage, sector KB CRUD, merge, promote
│   ├── test_core_classification.py # 15 testes — two-phase KB learning, merged KB pipeline (mock LLM)
│   ├── test_project_manager.py  # 29 testes — slugify, sector/project CRUD, delete_sector, use_sector_kb, resolve_hierarchy
│   └── test_utils.py            # 8 testes — safe_json_dumps, get_models_dir
│
├── pytest.ini                   # Config pytest (testpaths, addopts)
│
└── frontend/
    ├── jest.config.js            # Config Jest (next/jest, jsdom, path alias @/)
    ├── jest.setup.ts             # Setup jest-dom matchers
    └── src/
        ├── __tests__/
        │   ├── api.test.ts       # 8 testes — endpoints HTTP + sector KB (mock axios)
        │   └── useReview.test.ts # 15 testes — state machine de revisão (renderHook)
        ├── pages/taxonomy.tsx    # Página principal — 4 abas + state machine
        ├── hooks/
        │   ├── useTaxonomySession.ts # Lifecycle de sessão (project-aware)
        │   ├── useReview.ts          # State machine de revisão
        │   ├── useProjects.ts        # CRUD projetos/setores + IndexedDB
        │   ├── useHierarchy.ts       # Parse hierarquia → cascading dropdowns
        │   ├── useVirtualScroll.ts   # Windowing para 50K rows
        │   └── useCopilot.ts         # Integração Copilot (gated por revisão)
        ├── lib/
        │   ├── types.ts              # Tipos centralizados
        │   ├── api.ts                # Cliente HTTP (todos os endpoints)
        │   ├── database.ts           # IndexedDB schema v2
        │   ├── design-tokens.ts      # Design tokens (cores, gradientes, sombras, tipografia)
        │   └── smart-context/        # Smart Context RAG client-side (Copilot analytics)
        └── components/
            ├── project/              # ProjectSelect, CreateProjectModal, EditProjectModal
            ├── taxonomy/             # ClassifyTab, ReviewTab, KnowledgeTab, SectorKnowledgeTab, AnalyzePanel, KnowledgeSlideOver, ItemDetailPanel
            ├── layout/               # CollapsibleSidebar, ContextBar
            ├── chat/                 # ChatInput, ChatMessage, ChatLocked, SuggestedPrompts
            └── ui/                   # Design system (Button, Card, Tabs, Modal, Badge, SlideOver, Input, Select, Textarea, FilterDropdown, AiAvatar, StickyFooter, etc.)
```

---

## Constantes e Thresholds

```python
# worker_helpers.py
CHUNK_SIZE = 500              # Linhas por chunk
MAX_PARALLEL_CHUNKS = 5       # Chunks simultâneos (round-robin entre jobs)
MAX_PROCESSING_TIME = 20 * 60 # Budget de 20min por ciclo do worker
STALE_THRESHOLD_SECONDS = 3600  # Jobs PROCESSING > 1h → ERROR

# llm_classifier.py
LLM_BATCH_SIZE = 100          # Itens por chamada ao Grok
LLM_CONCURRENT_WORKERS = 20   # Threads paralelas
LLM_TIMEOUT_SECONDS = 90      # Timeout por chamada
LLM_MAX_RETRIES = 2           # Retries com backoff exponencial

# core_classification.py — Two-Phase KB Learning
KB_DIRECT_MATCH_THRESHOLD = 0.90   # Similaridade mínima para usar KB direto (sem LLM)
KB_ENRICHED_EXAMPLE_MIN_SIM = 0.30 # Similaridade mínima para incluir como exemplo enriched
KB_ENRICHED_MAX_EXAMPLES = 20      # Máximo de exemplos enriched por batch LLM

# core_classification.py / kb_retriever.py
FEW_SHOT_MAX_EXAMPLES = 10    # Exemplos representativos selecionados da KB (fallback global)
FEW_SHOT_PER_ITEM_K = 5       # Top-K por item na re-classificação

# knowledge_base.py
KB_DEDUP = "description_norm"  # Critério de deduplicação (apenas descrição — cada descrição tem 1 entrada)

# ml_classifier.py (caminho legado)
ML_CONFIDENCE_UNIQUE = 0.45
ML_CONFIDENCE_AMBIGUOUS = 0.25

# utils.py — Mapeamento de source → label amigável (UI e Excel)
# "KB (Direct Match)" → "Base de Aprendizado"
# "LLM (Batch)" / "LLM (Reclassified)" → "Grok"
# "Taxonomy (Dict)" → "Dicionário" / "ML" → "ML"
# Função: friendly_source_label(source) — usada em review_bp.py e worker_helpers.py
```

---

## Variáveis de Ambiente

```bash
# Azure Functions (local.settings.json)
FUNCTIONS_WORKER_RUNTIME=python
AzureWebJobsStorage=UseDevelopmentStorage=true

# Modelos
MODELS_DIR_PATH=               # Override do diretório de models (opcional)
USE_ML_CLASSIFIER=true

# Grok/xAI
GROK_API_KEY=
GROK_API_ENDPOINT=https://api.x.ai/v1
GROK_MODEL_NAME=grok-4-1-fast-reasoning

# Copilot Studio
DIRECT_LINE_SECRET=

# Power Automate (opcional)
POWER_AUTOMATE_URL=
POWER_AUTOMATE_API_KEY=

# Frontend (.env.local)
NEXT_PUBLIC_API_URL=http://localhost:7071/api
NEXT_PUBLIC_FUNCTION_KEY=
```

Resolução do `MODELS_DIR_PATH` (em `src/utils.py`):
1. Env var `MODELS_DIR_PATH` → usa se definida
2. `/mount/models` → usa se o diretório existir (Azure)
3. `./models/` relativo à raiz do projeto (desenvolvimento local)

---

## Desenvolvimento Local

### Backend

```bash
# Instalar dependências
pip install -r requirements.txt

# Copiar e preencher secrets
cp local.settings.json.example local.settings.json

# Rodar Azure Functions (requer Azure Functions Core Tools)
func start

# Ou worker local direto (sem o Functions host)
python run_local_worker.py
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # editar NEXT_PUBLIC_API_URL
npm run dev    # http://localhost:3000
```

### Testes

```bash
# Backend — 153 testes (pytest, ~4s)
python3 -m pytest tests/ -v

# Frontend — 23 testes (Jest + React Testing Library, ~1.3s)
cd frontend && npx jest --verbose

# Com coverage
python3 -m pytest tests/ --cov=src --cov-report=term-missing
cd frontend && npx jest --coverage
```

**Regra fundamental:** zero chamadas ao Grok/xAI nos testes. Módulos com dependência de LLM (`llm_classifier`, `core_classification`, `worker_helpers`) **não** são testados diretamente — validados indiretamente via `hierarchy_validator` e `kb_retriever`.

**Módulos cobertos (backend):** `preprocessing`, `hierarchy_validator`, `kb_retriever`, `knowledge_base`, `project_manager`, `utils`, `core_classification` (two-phase, com mock LLM)
**Módulos cobertos (frontend):** `lib/api.ts`, `hooks/useReview.ts`

---

## Schemas Chave

### sector_config.json
```json
{
  "name": "naval",
  "display_name": "Naval",
  "custom_hierarchy": null,
  "created_at": "2026-02-18T..."
}
```

### project_config.json
```json
{
  "project_id": "naval-wartsila",
  "display_name": "Naval - WÄRTSILÄ",
  "sector": "naval",
  "client_context": "Contexto do cliente para prompt LLM",
  "custom_hierarchy": [...],
  "hierarchy_source": "own",
  "hierarchy_filename": "hierarquia.xlsx",
  "created_at": "...",
  "updated_at": "...",
  "few_shot_max_examples": 5,
  "use_sector_kb": true
}
```

### knowledge_base.json (array)
```json
[{
  "id": "uuid",
  "description": "texto original",
  "description_norm": "texto normalizado",
  "N1": "...", "N2": "...", "N3": "...", "N4": "...",
  "source": "llm_approved|consultant_correction|reclassified_with_guidance",
  "confidence": 0.85,
  "instruction_used": null,
  "version": "v1",
  "date_added": "2026-02-18T..."
}]
```

---

## State Machine das 4 Abas (Frontend)

| Estado da sessão | Classificar | Revisar | Conhecimento | Analisar |
|-----------------|-------------|---------|--------------|---------|
| Sem sessão      | Ativo       | Locked  | Ativo        | Locked  |
| Processando     | Disabled    | Locked  | Locked       | Locked  |
| Classificado    | Ativo       | **Ativo** ← | Ativo   | Locked  |
| Em revisão      | Ativo       | Ativo   | Ativo        | Locked  |
| Revisão pronta  | Ativo       | Ativo   | Ativo        | **Ativo** ← |

---

## IndexedDB Schema v2

- `sessions` — adicionados campos: `reviewState`, `reviewedItems`, `approvedSummary`, `projectId`
- `projects` (novo) — key=`id`, indexes: `by-sector`, `by-name`
- `reviewProgress` (novo) — key=`sessionId`, persiste estados de revisão parcial

Migration v1→v2: sessões existentes recebem `reviewState: 'completed'` automaticamente.

---

## Convenções de Código

### Python (Backend)
- Módulos em `src/` com responsabilidade única
- `normalize_text()` em `preprocessing.py` é a source of truth — não duplicar
- Hierarquia customizada como **lista** de dicts (preserva N4s duplicados, ex: "Materiais OEM" em 18 marcas)
- `safe_json_dumps()` para toda serialização JSON com dados numéricos
- Logging via `logging` stdlib (nunca `print()`)
- Imports relativos: `from src.module import func`

### TypeScript (Frontend)
- Tipos centralizados em `frontend/src/lib/types.ts`
- Hooks em `frontend/src/hooks/` para toda lógica de estado
- API client centralizado em `frontend/src/lib/api.ts`
- Design tokens em `frontend/src/lib/design-tokens.ts`
- Download de arquivos: **sempre** base64 → `atob()` → `Uint8Array` → Blob **no momento do clique**. Nunca blob URLs pre-criados (`URL.createObjectURL`)
- TailwindCSS para estilização

### Design System — Paleta de Cores

O padrão visual é **Procurement Garage brand**: navy escuro + cyan-blue + purple AI. Design tokens centralizados em `frontend/src/lib/design-tokens.ts`.

**`tailwind.config.js` estende o tema com 4 escalas de cor:** `primary` (navy), `accent` (cyan-blue), `ai` (purple), `mint` (success). Zero classes `blue-*` no codebase.

| Uso | Cor |
|-----|-----|
| Sidebar background | `bg-gradient-to-b from-[#1c0957] via-[#180847] to-[#120535]` |
| Accent primário (tabs, botões, CTAs) | `#0693e3` / `accent-500` |
| Accent brilhante (hover, destaques) | `#38a8f5` / `accent-400` |
| Accent hover (botões) | `#0576b8` / `accent-600` |
| Accent light bg (badges, selection) | `#eff8ff` / `accent-50` |
| Gradiente signature (CTA principal) | `from-[#0693e3] to-[#9b51e0]` (cyan → purple) |
| AI/Copilot elements | `#9b51e0` / `ai-400` |
| Success states | `#2db17f` / `mint-500` |
| Focus rings | `focus:ring-accent-500/20` |
| Separadores no sidebar | `border-white/10` |
| Texto secundário no sidebar | `text-white/60`, `text-white/40` |
| Texto primário (headings) | `#32373c` |
| Texto secundário (body) | `#486581` |

### Design Tokens (`design-tokens.ts`)

Exporta objetos tipados para uso programático:
- `colors` — escalas navy, accent, ai, mint, text, background, status
- `gradients` — signature, sidebar, accent, mint, ai
- `shadows` — sm a xl, card, input, inputFocus, glow, glowAi
- `tw` — classes Tailwind compostas (glass, buttonPrimary, buttonAi, card, input, etc.)
- `iconColors` — cores semânticas para ícones
- `typography` — fontFamily (Inter), heading, body, caption

### Sidebar — Arquitetura

O sidebar usa o componente `CollapsibleSidebar` (`components/layout/CollapsibleSidebar.tsx`) com gradiente navy unificado, estado colapsável (pinned/unpinned) e sessões.

Composição da sidebar (de cima para baixo):
1. **Logo** — branding com textos em `text-white`
2. **ProjectSelect** — com `variant="dark"` obrigatório
3. **SessionSidebar** — apenas lista de sessões + footer (sem container próprio)

`CollapsibleSidebar` controla o gradiente, largura e bordas. `SessionSidebar` **não** define seu próprio `w-72`, `bg-gradient`, `border-r` ou `shadow`. Se adicionar outro uso de `SessionSidebar` em outro contexto, criar um wrapper separado.

### ContextBar — Barra Superior

O componente `ContextBar` (`components/layout/ContextBar.tsx`) renderiza a barra superior com:
- Breadcrumb: Setor → Projeto
- Step indicator: Classificar → Revisar → Analisar (visual do progresso)
- Botão de acesso à KB (abre o `KnowledgeSlideOver`)

### ProjectSelect — Prop `variant`

```tsx
<ProjectSelect variant="dark" />   // dentro do sidebar navy
<ProjectSelect variant="light" />  // padrão, fundo branco (futuro uso em modals)
```

### Auto-Slug de Setores

O `slug` (ID interno) do setor é gerado automaticamente no `CreateProjectModal` — usuárias **não** veem nem digitam o slug. A lógica é:

```typescript
// CreateProjectModal.tsx
const newSectorName = newSectorDisplay
  .toLowerCase()
  .normalize('NFD').replace(/[\u0300-\u036f]/g, '')  // remove acentos
  .replace(/[^a-z0-9]+/g, '-')
  .replace(/^-+|-+$/g, '');
// "Naval Offshore" → "naval-offshore"
// "Saúde & Bem-Estar" → "saude-bem-estar"
```

O hint `ID interno: naval-offshore` aparece em cinza claro sob o campo (visível mas discreto). **Nunca** solicitar slug às usuárias.

### Nomenclatura
- Níveis: N1 (mais alto) → N4 (mais granular)
- Status de classificação: `"Unico"`, `"Nenhum"` — **derivados** dos N1-N4 em `GetJobResults` (não armazenados no caminho LLM-direto). `"Ambiguo"` existe apenas no caminho legado de dicionário.
- Status de jobs: `PENDING`, `PROCESSING`, `CLASSIFIED`, `APPROVED`, `COMPLETED`, `ERROR`
- Setores: lowercase slug auto-gerado (`"naval"`, `"naval-offshore"`)
- Project IDs: slug gerado de `"{setor}-{nome-projeto}"` (ex: `"naval-wartsila"`)

---

## Pontos de Atenção Arquitetural

### Layout da Aba Analisar

A aba "Analisar" usa layout **chat-first** com flex vertical (não scroll geral):

```
┌─ Summary bar (1 linha) ──────── [Baixar Excel] ─┐
├─ Chat (flex-1 min-h-0, scroll interno) ──────────┤
├─ Input (flex-shrink-0, sticky bottom) ───────────┤
```

- Container: `flex flex-col overflow-hidden` (diferente das demais abas que usam `overflow-y-auto`)
- Summary compacto: `flex items-center justify-between` com stats inline (total, aprovados, editados, na base)
- Chat: `flex-1 min-h-0 overflow-y-auto` — preenche todo o espaço restante
- Input: `mt-4 flex-shrink-0` — sempre visível sem scroll

### Ao Modificar Código

- **Hierarquia como lista**: `_parse_custom_hierarchy_b64()` retorna **lista** (não dict) para preservar N4s duplicados. Não converter para dict.
- **Sort antes de chunking**: ordenar por `desc_col` (case-insensitive) antes de dividir em chunks — agrupa itens similares no mesmo batch LLM. Não remover.
- **KB mesclada carregada 1x por job**: `get_active_jobs()` em `worker_helpers.py` carrega KB do setor (se `use_sector_kb=true`) + KB do projeto, faz merge via `merge_kb_entries()` e armazena em `job_info["kb_entries"]`. `process_single_chunk()` não recarrega. O merge usa `description_norm` como chave — projeto sobrescreve setor.
- **Sector KB = referência viva**: Na classificação, o KB do setor é mesclado automaticamente com o do projeto (sem cópia), **condicionado ao toggle `use_sector_kb`** (default true). Novos projetos herdam imediatamente todas as entradas do setor. `ApproveClassifications` alimenta apenas KB do projeto — promoção para setor é ação separada e intencional via `PromoteToSectorKB`.
- **`use_sector_kb` condicional em 3 pontos**: (1) `worker_helpers.py:get_active_jobs()` — carregamento da KB do setor no worker; (2) `review_bp.py:reclassify_items_endpoint()` — KB do setor na reclassificação; (3) `knowledge_bp.py:get_kb_coverage_endpoint()` — cobertura inclui setor. Sempre ler `project_config.get("use_sector_kb", True)` com default True.
- **Sector KB CRUD completo**: Os 9 endpoints de setor em `knowledge_bp.py` (Get, Add, Update, Delete, Coverage, Versions, Rollback, Export, Import) + `PromoteToSectorKB` usam `entity_type="sector"` na classe `KnowledgeBase`. São cópias funcionais dos endpoints de projeto, trocando `projectId` → `sectorName`.
- **`_origin` no merge frontend**: `KnowledgeTab` faz merge de KB do projeto e setor, marcando cada entrada com `_origin: 'project' | 'sector' | 'both'`. Entradas com `_origin === 'both'` (existem no projeto E no setor) são tratadas como somente leitura no `KnowledgeTable` — sem checkbox de seleção para promoção, pois já estão no setor.
- **KnowledgeBase entity_type**: O construtor aceita `entity_type="project"` (default) ou `entity_type="sector"`. O path é resolvido automaticamente (`projects/` ou `sectors/`). Não há diferença funcional entre os dois tipos — mesmos métodos CRUD, versioning, etc.
- **CreateProjectModal 2 steps**: Wizard simplificado para 2 passos: (1) Dados básicos, (2) Hierarquia. Step 3 (KB seed) foi removido — projetos herdam KB do setor automaticamente.
- **Status CLASSIFIED**: `consolidate_job()` em `worker_helpers.py` define status `"CLASSIFIED"`, não `"COMPLETED"`. `ApproveClassifications` define `"COMPLETED"`. Não alterar sem revisar o fluxo.
- **Linhas em branco**: consolidação preenche NaN com `"Não Identificado"` (N1-N4). fillna de `status` é condicional (`if "status" in final_df.columns`) — só existe no caminho legado.
- **Colunas duplicadas**: remove colunas de classificação do chunk original **antes** do merge para evitar `N1.1`, `N2.1`, etc.
- **Download no frontend**: `approveClassifications` retorna `fileContentBase64`. O frontend converte para Blob no clique com `atob()` + `Uint8Array`. Não usar `fetch(dataUrl)`.
- **Copilot gated**: `useCopilot.ts` tem early return se `reviewCompleted !== true`. Não remover essa guarda.
- **Thresholds de confiança ML** (0.45/0.25 em `hybrid_classifier.py`) afetam toda a classificação legada — testar antes de alterar.
- **Prompts do Grok** em `llm_classifier.py`: quando `few_shot_examples` presente, adiciona bloco "EXEMPLOS CONFIRMADOS". Quando `user_instruction` presente, adiciona "INSTRUÇÃO ESPECÍFICA DO CONSULTOR". Não alterar ordem (exemplos antes da instrução).
- **Compatibilidade legada**: setores `varejo` e `educacional` usam caminho ML legado via `use_legacy_ml=True` em `core_classification.py`. Preservar.
- **Sidebar via CollapsibleSidebar**: `CollapsibleSidebar` em `components/layout/` controla todo o gradiente, largura e bordas do sidebar. `SessionSidebar` não tem container próprio — não adicionar `bg-*`, `w-72`, `border-r` ou `shadow` nele.
- **ProjectSelect no sidebar**: sempre passar `variant="dark"`. Sem essa prop, o componente renderiza fundo branco e fica visualmente inconsistente com o sidebar navy.
- **Slug de setor**: nunca expor o campo de slug para o usuário. Sempre gerar automaticamente a partir do display name em `CreateProjectModal`. Manter a lógica de `normalize('NFD')` para suportar acentos corretamente.
- **Zero classes `blue-*`**: todas substituídas por cores do design system. Não reintroduzir `blue-*` — usar `accent-*` (do tailwind config), `ai-*`, `mint-*`, ou valores diretos como `[#0693e3]`, `[#0576b8]`, `[#9b51e0]`.
- **Layout da aba Analisar**: usa `flex flex-col overflow-hidden` (diferente das demais abas). Não trocar para `overflow-y-auto` — quebraria o chat-first layout. O chat usa `flex-1 min-h-0` e o input usa `flex-shrink-0`.
- **Parâmetros API camelCase**: `knowledge_bp.py`, `review_bp.py` e `projects_bp.py` (GET params) usam camelCase (`projectId`, `entryId`, `pageSize`). `api.ts` deve enviar camelCase. Não introduzir snake_case (`project_id`) — causaria erro 400 silencioso.
- **KB dedup por description_norm apenas**: `add_entries()` usa `description_norm` como chave de dedup. Cada descrição tem no máximo 1 entrada na KB. Entradas com mesmo texto são atualizadas in-place se a fonte for igual ou mais autoritativa (consultant > reclassified > llm). Não reverter para dedup por `(description_norm, N4)` — causa acúmulo de duplicatas.
- **Two-Phase Classification**: `_llm_direct_pipeline()` em `core_classification.py` usa duas fases: (1) KB direct match (sim ≥ 0.90) classifica sem LLM; (2) itens restantes vão ao LLM com exemplos enriched. O `KBRetriever` é criado 1x por job em `get_active_jobs()` com a KB **mesclada** (setor + projeto) e reutilizado em todos os chunks. Não recriar o retriever por chunk — o TF-IDF indexing é o custo principal.
- **KB direct match não aplica na reclassificação**: `review_bp.py` usa enriched examples da KB **mesclada** (setor + projeto, se `use_sector_kb`) mas NÃO faz direct match (o consultor explicitamente quer re-classificar com instrução). Não adicionar Phase 1 na reclassificação.
- **select_enriched_examples limita 3 por N4**: para garantir diversidade nos exemplos enviados ao LLM. Não remover esse cap — sem ele, o LLM recebe exemplos homogêneos e perde contexto de outras categorias.
- **friendly_source_label()**: helper em `src/utils.py` que mapeia source interno (`"KB (Direct Match)"`, `"LLM (Batch)"`, etc.) para labels amigáveis (`"Base de Aprendizado"`, `"Grok"`, etc.). Usado em `review_bp.py` (Excel final) e `worker_helpers.py` (Excel intermediário). Frontend tem versão inline em `ReviewTable.tsx`.
- **Colunas dos Excels**: Excel final (ApproveClassifications) = Descricao, N1-N4, Fonte (label amigável). Sem Confianca nem Status Revisao. Excel intermediário (consolidate_job) = sem `status` nem `matched_terms`; `source` com label amigável. No caminho LLM-direto, `status` e `matched_terms` **não existem** nos result dicts — `_llm_direct_pipeline()` retorna apenas `description, N1-N4, source, confidence`. `GetJobResults` deriva `status` dos N1-N4 para compatibilidade com o frontend.
- **`status`/`matched_terms` removidos do LLM-direto**: `_llm_direct_pipeline()` em `core_classification.py` não emite mais `status` nem `matched_terms` nos result dicts (eram sempre `"Unico"` e `[]` — sem significado). `GetJobResults` em `classification_bp.py` deriva `status` dos N1-N4 (`"Nenhum"` se algum nível é vazio/"Não Identificado", senão `"Unico"`). O caminho legado (`_legacy_ml_pipeline`) continua emitindo esses campos. Não reintroduzir `status`/`matched_terms` no LLM-direto.
- **`generate_analytics()` simplificado**: `taxonomy_engine.py` retorna apenas Pareto (N1-N4). Seções `gaps` e `ambiguity` retornam `[]` por compatibilidade de schema — eram conceitos do dicionário legado. Não reintroduzir lógica de `Match_Type` no analytics.
- **`generate_summary()` deriva de N1-N4**: contagem `unico`/`nenhum` é calculada diretamente dos valores N1-N4 (sem depender de `status` ou `Match_Type`). `ambiguo` é sempre 0 no caminho LLM-direto. Campo mantido por compat.
- **`execution-engine.ts` usa `status` (não `Match_Type`)**: o campo `Match_Type` existia apenas no `classify_items()` do dicionário legado. Items vindos da API (`GetJobResults`) têm campo `status`. O CATEGORY_LOOKUP e DISTRIBUTION usam `i.status === 'Unico'`/`'Nenhum'`.
- **Reclassificação marca como `pending`, não `rejected`**: `handleReclassify` em `ReviewTab.tsx` usa `reclassifyItems()` (não `rejectItems()`). Itens reclassificados voltam como pendentes para o consultor aprovar a nova classificação. Usar `rejectItems()` aqui faria os itens serem excluídos do Excel final e da KB. O botão "Só Rejeitar" no `RejectModal` continua usando `rejectItems()` — comportamento correto para descartar.
- **KnowledgeSlideOver com abas**: O `KnowledgeSlideOver` em `components/taxonomy/` abre como painel lateral e contém duas abas internas: "Projeto" (`KnowledgeTab`) e "Setor ({display_name})" (`SectorKnowledgeTab`). Estado `kbTab: 'project' | 'sector'` em `taxonomy.tsx`. Se `use_sector_kb === false`, a aba Setor mostra empty state.
- **Smart Context RAG**: O subsistema `frontend/src/lib/smart-context/` (5 arquivos) implementa RAG client-side para o Copilot: `entity-extractor.ts` parseia intenções, `intent-router.ts` roteia, `execution-engine.ts` executa sobre itens classificados. Tipos: COUNT, TOP_N, DISTRIBUTION, TERM_SEARCH, CATEGORY_LOOKUP, etc.
- **UI components library**: `components/ui/` contém 17+ componentes reutilizáveis. Novos no redesign: `SlideOver` (painel lateral), `Input`/`Select`/`Textarea` (formulários), `FilterDropdown` (filtros multi-select), `AiAvatar` (avatar do Copilot), `StickyFooter` (rodapé fixo). Todos seguem design tokens.
- **`delete_sector()` com proteção**: `project_manager.py` — se `force=False` e há projetos no setor, levanta `ValueError` com lista de project_ids. Se `force=True`, deleta todos os projetos primeiro (`shutil.rmtree` em cada um) e depois o setor. Endpoint `DELETE /api/DeleteSector?sectorName=xxx&force=false` retorna 409 (conflito) quando há projetos sem force. Frontend mostra `ConfirmDialog` com lista dos projetos afetados.
- **ProjectSelect mostra setores vazios**: `bySector` em `ProjectSelect.tsx` inclui todos os setores (via `useMemo` com `sectors` + `projects`), não apenas os que têm projetos. Setores vazios mostram "Nenhum projeto" em itálico. Botão de excluir setor sempre visível ao lado do header do grupo (`text-white/15`, hover vermelho).
- **`hierarchy_source` enviado na criação**: `CreateProjectModal` mapeia `hierarchyOption` (`upload`→`own`, `inherit`→`inherited`, `none`→`padrao`) e envia `hierarchy_source` ao backend. Sem esse mapeamento, o backend defaulta para `"own"` e o `EditProjectModal` mostra "Hierarquia: Própria" incorretamente.

### Problemas Conhecidos

- Todos os endpoints usam `AuthLevel.ANONYMOUS` — em produção, restringir.
- Jobs usam filesystem como fila — não escala horizontalmente. Considerar Azure Queue Storage no futuro.
- Cache de modelo ML (`_MODEL_CACHE`) é in-memory e não persiste entre instâncias Functions.

---

## Regras de Commit

- **NUNCA** adicionar `"Co-Authored-By"` nos commits.
- Mensagens em português, descritivas do que foi alterado.
- Prefixos sugeridos: `Fix`, `Ajuste`, `Adicionando`, `Refactor`

---

## Deployment

Push para `main` dispara deploy automático via GitHub Actions:
- **Frontend**: Azure Static Web Apps (build Next.js com output estático)
- **Backend**: Azure Functions App (deploy separado via `func azure functionapp publish`)

Ver `docs/DEPLOYMENT.md` para guia completo.

---

## Histórico de Bugs Resolvidos (v3)

| Data | Bug | Causa | Fix |
|------|-----|-------|-----|
| 2026-02-18 | Colunas duplicadas no Excel (N1.1, etc.) | Merge duplicava colunas de classificação | Remove colunas do chunk original antes do merge |
| 2026-02-18 | Download Excel 0KB | `fetch(dataUrl)` falhava silenciosamente | `atob()` + `Uint8Array` sob demanda no clique |
| 2026-02-18 | N4s duplicados perdidos (OEM por marca) | Hierarquia como dict keyed por N4 | Hierarquia como lista (preserva duplicatas) |
| 2026-02-18 | Itens iguais classificados diferente | batch_size pequeno espalhava similares | Sort por descrição + batch_size=100 |
| 2026-02-18 | Linhas em branco no Excel | NaN não preenchidos na consolidação | Preenche com "Não Identificado" na consolidação |
| 2026-02-18 | Sidebar com dois estilos conflitantes (branco em cima, navy embaixo) | `aside` com `bg-white` + `SessionSidebar` com gradiente navy próprio | `aside` unificado com gradiente navy; `SessionSidebar` sem container próprio |
| 2026-02-18 | Campo de slug técnico exposto a usuárias não técnicas | `CreateProjectModal` exibia dois campos: "nome-setor (slug)" e "Nome de Exibição" | Removido campo slug; gerado automaticamente com `normalize('NFD')` + regex |
| 2026-02-19 | Cores inconsistentes (blue-600 genérico em ~50 classes) | `tailwind.config.js` mapeava `primary` para azuis genéricos; ~50 classes `blue-*` espalhadas em 15 componentes | Sincronizado `primary` com navy, adicionado `accent` cyan; substituídas todas as classes `blue-*` por `[#14919b]`/`[#e0fcff]`/etc. |
| 2026-02-19 | Landing page com cores purple/blue | `index.tsx` usava `primary-*` que mapeava para azuis genéricos + shadow rgba purple | Migrado accent elements para `accent-*` (cyan); corrigido shadow rgba para `(20,145,155,*)` |
| 2026-02-19 | Aba Analisar com layout empilhado e chat limitado | Summary em 4 cards + download card + chat com `max-h-[55vh]`; input requeria scroll | Layout chat-first: summary compacto 1 linha, chat flex-1, input sticky bottom |
| 2026-02-19 | Botões sem focus ring visível | `Button.tsx` não tinha `focus:ring-*` styles | Adicionado `focus:outline-none focus:ring-2 focus:ring-[#14919b]/25 focus:ring-offset-1` |
| 2026-02-19 | Zero testes no projeto | Nenhuma infraestrutura de testes configurada | pytest (141 testes backend) + Jest/RTL (23 testes frontend) |
| 2026-02-19 | KB vazia apesar de aprovações bem-sucedidas | `api.ts` enviava snake_case (`project_id`) mas backend esperava camelCase (`projectId`) em todos os 9 endpoints de KB | Corrigidos todos os nomes de parâmetros em `api.ts` (KB + 3 endpoints de projetos) |
| 2026-02-19 | KB acumulando duplicatas (70 entradas de 24 linhas) | Dedup usava `(description_norm, N4)` como chave; LLM dava N4 diferente a cada aprovação, bypassando o dedup | Dedup alterado para `description_norm` apenas; entrada atualizada in-place se fonte igual ou mais autoritativa |
| 2026-02-19 | `kb_added` não exibido no summary da aba Analisar | `ApproveClassifications` retornava `kb_added` fora do dict `summary`; frontend usava `result.summary.kb_added` (undefined) | Adicionado `kb_added` dentro do dict `summary` na resposta |
| 2026-02-19 | Fonte da classificação não visível na revisão | `source` fluía ao frontend mas não era exibido na `ReviewTable` | Coluna FONTE com badge colorido (cyan=KB, roxo=Grok) na `ReviewTable`; `friendly_source_label()` em `utils.py` |
| 2026-02-19 | Excel com colunas irrelevantes (Confianca, Status Revisao, status, matched_terms) | Colunas legadas do caminho ML incluídas nos Excels mesmo no caminho LLM-direto | Excel final: removidas Confianca e Status Revisao; Excel intermediário: removidas status e matched_terms; source com label amigável em ambos |
| 2026-02-19 | KB isolada por projeto sem compartilhamento entre projetos do mesmo setor | KB existia apenas a nível de projeto; `kb_seed_from` copiava de outro projeto (arriscado) | KB a nível de setor (referência viva): merge automático setor+projeto na classificação; promoção seletiva de entradas; `kb_seed_from` removido; `CreateProjectModal` simplificado de 3→2 steps |
| 2026-02-19 | Itens reclassificados excluídos do Excel final e da KB | `handleReclassify` em `ReviewTab.tsx` chamava `rejectItems()` após receber resultado do Grok, marcando item como `rejected` — filtrado na finalização | Adicionada função `reclassifyItems()` em `useReview.ts` que marca como `pending` (preservando `instructionUsed`); `handleReclassify` agora usa `reclassifyItems()` ao invés de `rejectItems()` |
| 2026-02-19 | `status` sempre `"Unico"` e `matched_terms` sempre `[]` no caminho LLM-direto (campos sem significado) | Conceitos herdados do v2 (dicionário+ML detectava ambiguidade real); no LLM-direto o Grok sempre escolhe uma classificação | Removidos `status`/`matched_terms` de `_llm_direct_pipeline()`; `generate_summary()` deriva unico/nenhum dos N1-N4; `generate_analytics()` retorna gaps/ambiguity vazios; `GetJobResults` deriva `status` dos N1-N4; `execution-engine.ts` corrigido de `Match_Type` para `status` |
| 2026-02-20 | Entradas `_origin === 'both'` apareciam com checkbox para promoção ao setor | `KnowledgeTable` tratava apenas `_origin === 'sector'` como somente leitura; entradas existentes em ambos os KBs ficavam selecionáveis | Expandido `isSector` para incluir `'both'`; `handleSelectAllProject` e header checkbox filtram apenas `_origin === 'project'` |
| 2026-02-20 | KB do setor sem CRUD na UI (100% read-only) | Só existia `PromoteToSectorKB` como escrita; consultor não conseguia editar/deletar/limpar entradas | +9 endpoints backend (Update, Delete, Rollback, Add, Coverage, Versions, Export, Import para setor) + `SectorKnowledgeTab` no frontend com gestão completa |
| 2026-02-20 | KB do setor sempre mesclada sem opção de desabilitar | Merge automático hardcoded em `worker_helpers.py` e `review_bp.py`; projetos não podiam usar KB isolada | Toggle `use_sector_kb` no `project_config.json` (default true); condicional em worker, reclassificação e cobertura; toggle switch no Create/EditProjectModal |
| 2026-02-24 | Sem forma de excluir setores via API ou UI | Só existia `DeleteProject`; setores vazios não apareciam no dropdown | `delete_sector()` com proteção force/no-force; endpoint `DELETE /api/DeleteSector`; `ProjectSelect` mostra todos os setores + botão excluir; `ConfirmDialog` com lista de projetos afetados |
| 2026-02-24 | Hierarquia sempre "Própria" no EditProjectModal | `CreateProjectModal` não enviava `hierarchy_source`; backend defaultava para `"own"` | Adicionado mapeamento `hierarchyOption` → `hierarchy_source` (`upload`→`own`, `inherit`→`inherited`, `none`→`padrao`) no `handleCreate()` |
