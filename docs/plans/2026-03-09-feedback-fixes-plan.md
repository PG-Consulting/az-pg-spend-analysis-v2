# Feedback Fixes (2026-03-09) — Plano de Implementação (v2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Corrigir 3 bugs reportados pelo cliente: fornecedor não visível na tela, chat do copilot não limpa, e deploy pendente.

**Architecture:** Fix 1 requer mudança backend (GetJobResults) + frontend (types + ReviewTable). Fix 2 é frontend-only (useCopilot + taxonomy.tsx + AnalyzeTab). Fix 3 é operacional (deploy).

**Tech Stack:** Python (Azure Functions), TypeScript (Next.js 14 + React 18), TailwindCSS

**Revisão v2:** Corrigido após plan-critic — 4 CRITICALs resolvidos: (1) teste standalone sem `self`, (2) sem index signature em ClassifiedItem — usa cast localizado, (3) código concreto para AnalyzeTab, (4) auto-limpeza do chat ao trocar sessão.

---

## Task 1: Backend — Incluir extra_columns no GetJobResults

**Contexto:** `consolidate_job()` salva TODAS as colunas (incluindo "Fornecedor") no `result.json` via `final_df.to_dict(orient="records")`. Porém `GetJobResults` (classification_bp.py:295-403) constrói items manualmente com apenas index/description/N1-N4/confidence/source/status, descartando colunas extras. Precisamos incluí-las.

**Files:**
- Modify: `blueprints/classification_bp.py` (função GetJobResults)
- Test: `tests/test_classification_bp.py`

**Step 1: Escrever o teste**

Em `tests/test_classification_bp.py`, adicionar uma nova classe `TestGetJobResults` com teste standalone (sem `self` problemático):

```python
class TestGetJobResults:
    """Testes para o endpoint GetJobResults."""

    def test_extra_columns_included(self, tmp_path, monkeypatch):
        """GetJobResults deve retornar extra_columns e dados extras nos items."""
        from blueprints.classification_bp import GetJobResults

        jobs_dir = tmp_path / "taxonomy_jobs"
        job_dir = jobs_dir / "job-extra"
        job_dir.mkdir(parents=True)

        status = {
            "status": "CLASSIFIED",
            "total_chunks": 1,
            "desc_column": "Descricao",
            "extra_columns": ["Fornecedor", "Centro de Custo"],
        }
        (job_dir / "status.json").write_text(json.dumps(status))

        result = {
            "items": [
                {
                    "Descricao": "Parafuso M10",
                    "Fornecedor": "ABC Ltda",
                    "Centro de Custo": "CC-001",
                    "N1": "MRO", "N2": "Fixadores", "N3": "Parafusos", "N4": "Parafuso Métrico",
                    "confidence": 0.85, "source": "Grok",
                },
                {
                    "Descricao": "Tinta spray",
                    "Fornecedor": "XYZ SA",
                    "Centro de Custo": "CC-002",
                    "N1": "MRO", "N2": "Tintas", "N3": "Spray", "N4": "Tinta Industrial",
                    "confidence": 0.70, "source": "Base de Aprendizado",
                },
            ],
            "analytics": {"pareto": []},
            "summary": {"total_linhas": 2},
        }
        (job_dir / "result.json").write_text(json.dumps(result))

        monkeypatch.setattr("blueprints.classification_bp.get_jobs_dir", lambda: str(jobs_dir))

        req = MagicMock()
        req.method = "GET"
        req.params = {"jobId": "job-extra"}

        resp = GetJobResults(req)
        data = json.loads(resp.get_body())

        assert data["extra_columns"] == ["Fornecedor", "Centro de Custo"]
        assert data["items"][0]["Fornecedor"] == "ABC Ltda"
        assert data["items"][0]["Centro de Custo"] == "CC-001"
        assert data["items"][1]["Fornecedor"] == "XYZ SA"

    def test_no_extra_columns_backward_compat(self, tmp_path, monkeypatch):
        """Sem extra_columns no status, resposta deve ter extra_columns=[]."""
        from blueprints.classification_bp import GetJobResults

        jobs_dir = tmp_path / "taxonomy_jobs"
        job_dir = jobs_dir / "job-noextra"
        job_dir.mkdir(parents=True)

        status = {
            "status": "CLASSIFIED",
            "total_chunks": 1,
            "desc_column": "Descricao",
        }
        (job_dir / "status.json").write_text(json.dumps(status))

        result = {
            "items": [
                {"Descricao": "Item A", "N1": "X", "N2": "Y", "N3": "Z", "N4": "W",
                 "confidence": 0.9, "source": "Grok"},
            ],
            "analytics": {"pareto": []},
            "summary": {"total_linhas": 1},
        }
        (job_dir / "result.json").write_text(json.dumps(result))

        monkeypatch.setattr("blueprints.classification_bp.get_jobs_dir", lambda: str(jobs_dir))

        req = MagicMock()
        req.method = "GET"
        req.params = {"jobId": "job-noextra"}

        resp = GetJobResults(req)
        data = json.loads(resp.get_body())

        assert data["extra_columns"] == []
        assert "Fornecedor" not in data["items"][0]
```

**Step 2: Rodar teste para verificar que falha**

```bash
python3 -m pytest tests/test_classification_bp.py::TestGetJobResults -v
```
Expected: FAIL — `extra_columns` não existe na resposta

**Step 3: Implementar no GetJobResults**

Em `blueprints/classification_bp.py`, função `GetJobResults`:

1. Após `status_data = read_status(status_file)` (linha ~320), adicionar:
```python
extra_columns = status_data.get("extra_columns", [])
```

2. No branch CLASSIFIED/COMPLETED (linhas ~343-356), modificar o loop para incluir extra_columns:
```python
if job_status in ("CLASSIFIED", "COMPLETED") and result_json:
    raw_items = result_json.get("items", [])
    for idx, row in enumerate(raw_items):
        item = {
            "index": idx,
            "description": row.get(desc_col, row.get("description", "")),
            "N1": row.get("N1", "Não Identificado"),
            "N2": row.get("N2", "Não Identificado"),
            "N3": row.get("N3", "Não Identificado"),
            "N4": row.get("N4", "Não Identificado"),
            "confidence": row.get("confidence", 0.0),
            "source": row.get("source", ""),
            "status": _derive_status(row),
        }
        for col in extra_columns:
            item[col] = row.get(col, "")
        items.append(item)
```

3. Na resposta (linhas ~394-401), adicionar `extra_columns`:
```python
response = {
    "jobId": job_id,
    "status": job_status,
    "items": items,
    "total": len(items),
    "analytics": analytics,
    "summary": summary,
    "extra_columns": extra_columns,
}
```

**Step 4: Rodar teste para verificar que passa**

```bash
python3 -m pytest tests/test_classification_bp.py::TestGetJobResults -v
```
Expected: PASS

**Step 5: Rodar todos os testes backend**

```bash
python3 -m pytest tests/ -v
```
Expected: 267+ testes PASS

**Step 6: Commit**

```bash
git add blueprints/classification_bp.py tests/test_classification_bp.py
git commit -m "Fix: inclui extra_columns (Fornecedor etc.) na resposta de GetJobResults"
```

---

## Task 2: Frontend — Tipos e prop drilling para extra_columns

**Contexto:** O backend agora retorna `extra_columns: string[]` e valores extras em cada item. O frontend precisa propagar até a ReviewTable. **NÃO adicionar index signature ao ClassifiedItem** — isso degradaria type safety. Em vez disso, usar `extraColumns` como metadado separado e acessar valores via cast localizado `(item as any)[col]` apenas no ReviewTable.

**Files:**
- Modify: `frontend/src/lib/types.ts` (TaxonomySession — adicionar extraColumns)
- Modify: `frontend/src/lib/api.ts` (return type de getJobResults)
- Modify: `frontend/src/hooks/useTaxonomySession.ts` (salvar extraColumns na session)
- Modify: `frontend/src/components/taxonomy/ReviewTab.tsx` (aceitar e passar extraColumns)
- Modify: `frontend/src/pages/taxonomy.tsx` (passar extraColumns ao ReviewTab)

**Step 1: Adicionar `extraColumns` ao TaxonomySession em types.ts**

Em `frontend/src/lib/types.ts`, no tipo `TaxonomySession` (linha ~86-107), adicionar:

```typescript
export interface TaxonomySession {
  // ... campos existentes ...
  approvedDownloadFilename?: string;
  /** Extra column names from the uploaded file (e.g. ["Fornecedor"]) */
  extraColumns?: string[];
}
```

**NÃO alterar ClassifiedItem** — manter o tipo limpo.

**Step 2: Atualizar return type de getJobResults em api.ts**

Em `frontend/src/lib/api.ts`, na função `getJobResults` (linha ~394-402), atualizar o tipo de retorno:

```typescript
async getJobResults(
  jobId: string
): Promise<{ jobId: string; status: string; items: ClassifiedItem[]; total: number; analytics?: any; summary?: any; extra_columns?: string[] }> {
```

**Step 3: Salvar extraColumns na session (useTaxonomySession.ts)**

No `handleFileSelect` (linha ~142-157), ao criar `newSession`:

```typescript
const newSession: TaxonomySession = {
    sessionId: jobId,
    jobId,
    filename: file.name,
    timestamp: Date.now(),
    projectId: activeProjectId || undefined,
    jobStatus: 'CLASSIFIED',
    summary: results.summary,
    analytics: results.analytics,
    items: results.items,
    extraColumns: results.extra_columns || [],
    downloadFilename: status.download_filename,
    fileContentBase64: status.file_content_base64,
    reviewState: 'pending',
    reviewedCount: 0,
    totalItems: results.total,
}
```

**Step 4: Passar extraColumns para ReviewTab (taxonomy.tsx)**

No JSX onde `<ReviewTab>` é renderizado (linha ~465-474):

```tsx
<ReviewTab
  sessionId={typedSession.sessionId}
  items={typedSession.items as ClassifiedItem[]}
  hierarchy={projectHierarchy}
  jobId={typedSession.jobId || ''}
  projectId={activeProjectId || ''}
  extraColumns={typedSession.extraColumns}
  onFinalizeReview={handleFinalizeReview}
  onReclassify={handleReclassify}
  isApproving={isApproving}
/>
```

**Step 5: Propagar em ReviewTab → ReviewTable (ReviewTab.tsx)**

Adicionar `extraColumns` à interface `ReviewTabProps` (linha ~11-29):

```typescript
interface ReviewTabProps {
  sessionId: string;
  items: ClassifiedItem[];
  hierarchy: HierarchyEntry[] | null;
  jobId: string;
  projectId: string;
  extraColumns?: string[];
  // ... resto mantém igual ...
}
```

Destructure (linha ~31-34):

```typescript
export function ReviewTab({
  sessionId, items, hierarchy, jobId, projectId,
  extraColumns = [],
  onFinalizeReview, onReclassify, isApproving = false,
}: ReviewTabProps) {
```

Passar para `<ReviewTable>` (linha ~342-352):

```tsx
<ReviewTable
  items={displayItems}
  getItemState={getItemState}
  activeIndex={activeIndex}
  selectedIndices={selectedIndices}
  extraColumns={extraColumns}
  onSelectItem={(index) => setActiveIndex(index)}
  onToggleSelect={toggleSelection}
  onApprove={approveItem}
  searchQuery={searchQuery}
  containerHeight={500}
/>
```

**Step 6: Rodar build para verificar tipos**

```bash
cd frontend && npx tsc --noEmit
```
Expected: sem erros de tipo

**Step 7: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/hooks/useTaxonomySession.ts frontend/src/components/taxonomy/ReviewTab.tsx frontend/src/pages/taxonomy.tsx
git commit -m "Refactor: propaga extra_columns (Fornecedor) do backend até ReviewTable"
```

---

## Task 3: Frontend — Renderizar extra_columns na ReviewTable

**Contexto:** A ReviewTable usa virtual scroll com grid CSS fixo `grid-cols-[36px_1fr_200px_48px]`. Precisamos adicionar colunas dinâmicas entre "Descrição" e "Classificação". O grid será dinâmico baseado no número de extra columns. Para acessar valores dinâmicos sem poluir o tipo `ClassifiedItem`, usamos `(item as any)[col]` — cast localizado apenas aqui.

**Files:**
- Modify: `frontend/src/components/taxonomy/ReviewTable.tsx`

**Step 1: Adicionar extraColumns à interface e calcular grid**

Na interface `ReviewTableProps` (linha ~8-18):

```typescript
interface ReviewTableProps {
  items: ClassifiedItem[];
  getItemState: (index: number) => ReviewItemState;
  activeIndex: number | null;
  selectedIndices: Set<number>;
  extraColumns?: string[];
  onSelectItem: (index: number) => void;
  onToggleSelect: (index: number) => void;
  onApprove: (index: number) => void;
  searchQuery?: string;
  containerHeight?: number;
}
```

No destructuring do componente (linha ~54-64):

```typescript
export function ReviewTable({
  items,
  getItemState,
  activeIndex,
  selectedIndices,
  extraColumns = [],
  onSelectItem,
  onToggleSelect,
  onApprove,
  searchQuery,
  containerHeight = 600,
}: ReviewTableProps) {
```

Após o destructuring, calcular o grid dinâmico:

```typescript
// Dynamic grid: checkbox + description + [extras] + classification + status
const extraColsTemplate = extraColumns.map(() => '140px').join(' ');
const gridTemplate = extraColumns.length > 0
  ? `36px 1fr ${extraColsTemplate} 200px 48px`
  : '36px 1fr 200px 48px';
const gridStyle = { gridTemplateColumns: gridTemplate };
```

**Step 2: Atualizar o header (linha ~86)**

Substituir:
```tsx
<div className="grid grid-cols-[36px_1fr_200px_48px] gap-0 px-3 py-2.5 bg-gray-50/80 border-b border-gray-100 flex-shrink-0">
```

Por:
```tsx
<div className="grid gap-0 px-3 py-2.5 bg-gray-50/80 border-b border-gray-100 flex-shrink-0" style={gridStyle}>
```

E após o div "Descrição" (depois da linha ~108), antes do div "Classificação", inserir:

```tsx
{extraColumns.map(col => (
  <div key={col} className="text-[11px] font-medium text-primary-400 uppercase tracking-wider flex items-center truncate">
    {col}
  </div>
))}
```

**Step 3: Atualizar as linhas (rows) — linha ~138-192**

No div da row (linha ~141), substituir:
```tsx
className={[
  'grid grid-cols-[36px_1fr_200px_48px] gap-0 px-3 items-center ...',
```

Por estilo inline + classes sem grid-cols:
```tsx
style={{
  position: 'absolute',
  top: absIdx * ROW_HEIGHT,
  width: '100%',
  height: ROW_HEIGHT,
  ...gridStyle,
  display: 'grid',
}}
className={[
  'gap-0 px-3 items-center cursor-pointer transition-colors duration-100 border-l-[3px] border-b border-b-gray-50',
  confidenceBorder,
  isActive
    ? 'bg-accent-50 border-l-accent-500'
    : isSelected
      ? 'bg-accent-50/50'
      : 'hover:bg-gray-50/60',
  decision === 'rejected' ? 'opacity-50' : '',
].join(' ')}
```

E após o div "Description" (linha ~167-170), antes do div "Classification" (linha ~172), inserir:

```tsx
{/* Extra columns */}
{extraColumns.map(col => (
  <div key={col} className="text-xs text-primary-500 truncate pr-2" title={String((item as any)[col] || '')}>
    {(item as any)[col] || <span className="text-gray-300">--</span>}
  </div>
))}
```

**Nota:** `(item as any)[col]` é o cast localizado — seguro aqui pois `col` vem de `extra_columns` validado pelo backend.

**Step 4: Rodar build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```
Expected: sem erros

**Step 5: Commit**

```bash
git add frontend/src/components/taxonomy/ReviewTable.tsx
git commit -m "Fix: exibe colunas extras (Fornecedor etc.) na tabela de revisão"
```

---

## Task 4: Frontend — Fix resetChat + auto-limpeza ao trocar sessão

**Contexto:** `resetChat()` em `useCopilot.ts` (linha 157-161) só reseta flags de loading/sending e input. `copilotMessages` e `chatHistory` NÃO são limpos. Além disso, o `useEffect` que carrega chat do localStorage (linhas 137-146) deveria limpar o localStorage da sessão anterior para evitar acúmulo.

**Files:**
- Modify: `frontend/src/hooks/useCopilot.ts`

**Step 1: Expandir resetChat para limpar tudo**

Substituir `resetChat` (linhas 157-161):

```typescript
// ANTES:
const resetChat = useCallback(() => {
    setIsCopilotLoading(false)
    setIsSending(false)
    setUserMessage('')
}, [])
```

```typescript
// DEPOIS:
const resetChat = useCallback(() => {
    setIsCopilotLoading(false)
    setIsSending(false)
    setUserMessage('')
    setCopilotMessages([])
    setChatHistory([])
    if (sessionId) {
        localStorage.removeItem(`${STORAGE_PREFIX}${sessionId}`)
    }
}, [sessionId])
```

**Step 2: Rodar build**

```bash
cd frontend && npx tsc --noEmit
```
Expected: sem erros

**Step 3: Commit**

```bash
git add frontend/src/hooks/useCopilot.ts
git commit -m "Fix: resetChat agora limpa mensagens, histórico e localStorage"
```

---

## Task 5: Frontend — Botão "Limpar Chat" no AnalyzeTab + wiring

**Contexto:** Precisamos: (1) destructurar `resetChat` do `useCopilot` em `taxonomy.tsx`, (2) passar para `AnalyzeTab`, (3) adicionar botão "Limpar Chat" ao AnalyzeTab. Código concreto para cada mudança.

**Files:**
- Modify: `frontend/src/pages/taxonomy.tsx` (destructure + prop)
- Modify: `frontend/src/components/taxonomy/AnalyzeTab.tsx` (prop + botão)

**Step 1: Destructurar resetChat em taxonomy.tsx**

Na linha ~228-236 de `taxonomy.tsx`, adicionar `resetChat`:

```typescript
const {
    copilotMessages,
    isCopilotLoading,
    isSending,
    userMessage,
    setUserMessage,
    sendUserMessage,
    generateExecutiveSummary,
    resetChat,
} = useCopilot({ activeSession: activeSession ?? null, reviewCompleted })
```

**Step 2: Passar resetChat para AnalyzeTab em taxonomy.tsx**

No JSX do AnalyzeTab (linhas ~488-501):

```tsx
<AnalyzeTab
  reviewSummary={typedSession?.reviewSummary ?? null}
  approvedFileContentBase64={typedSession?.approvedFileContentBase64}
  approvedDownloadFilename={typedSession?.approvedDownloadFilename}
  copilotMessages={copilotMessages}
  isCopilotLoading={isCopilotLoading}
  isSending={isSending}
  userMessage={userMessage}
  onSetUserMessage={setUserMessage}
  onSendMessage={sendUserMessage}
  onResetChat={resetChat}
  onClose={() => { setActiveSessionId(null); setActiveTab('classify') }}
  chatContainerRef={chatContainerRef}
/>
```

**Step 3: Atualizar AnalyzeTab — props + botão**

Em `frontend/src/components/taxonomy/AnalyzeTab.tsx`:

1. Adicionar `onResetChat` à interface `AnalyzeTabProps` (linha ~15-27):

```typescript
interface AnalyzeTabProps {
  reviewSummary: ReviewSummary | null
  approvedFileContentBase64?: string | null
  approvedDownloadFilename?: string | null
  copilotMessages: Message[]
  isCopilotLoading: boolean
  isSending: boolean
  userMessage: string
  onSetUserMessage: (msg: string) => void
  onSendMessage: (msg: string) => void
  onResetChat?: () => void
  onClose: () => void
  chatContainerRef: React.RefObject<HTMLDivElement>
}
```

2. Destructure (linha ~29-41):

```typescript
export default function AnalyzeTab({
  reviewSummary,
  approvedFileContentBase64,
  approvedDownloadFilename,
  copilotMessages,
  isCopilotLoading,
  isSending,
  userMessage,
  onSetUserMessage,
  onSendMessage,
  onResetChat,
  onClose,
  chatContainerRef,
}: AnalyzeTabProps) {
```

3. Adicionar botão "Limpar Chat" no header (linha ~58-82), entre o botão "Baixar Excel" e o botão "Fechar":

```tsx
<div className="flex items-center gap-2 flex-shrink-0">
  {approvedFileContentBase64 && approvedDownloadFilename && (
    <button
      onClick={() => {
        downloadBase64AsFile(approvedFileContentBase64!, approvedDownloadFilename!)
      }}
      className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-mint-500 text-white rounded-xl hover:bg-mint-600 transition-colors"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
      Baixar Excel
    </button>
  )}
  {onResetChat && copilotMessages.length > 0 && (
    <button
      onClick={onResetChat}
      title="Limpar conversa"
      className="w-8 h-8 flex items-center justify-center rounded-lg text-primary-400 hover:text-[#32373c] hover:bg-gray-100 transition-colors"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
    </button>
  )}
  <button
    onClick={onClose}
    title="Fechar análise"
    className="w-8 h-8 flex items-center justify-center rounded-lg text-primary-400 hover:text-[#32373c] hover:bg-gray-100 transition-colors"
  >
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  </button>
</div>
```

**Step 4: Rodar build e testes**

```bash
cd frontend && npx tsc --noEmit && npm run build
cd frontend && npx jest --verbose
```
Expected: sem erros, 50+ testes PASS

**Step 5: Commit**

```bash
git add frontend/src/pages/taxonomy.tsx frontend/src/components/taxonomy/AnalyzeTab.tsx
git commit -m "Fix: adiciona botão 'Limpar Chat' no AnalyzeTab e conecta resetChat"
```

---

## Task 6: Deploy e Validação

**Contexto:** Os fixes de "Não Identificado" e coluna "Fonte" no Excel já existem no código (commits anteriores) mas possivelmente não foram deployados. Este task é operacional.

**Step 1: Rodar todos os testes**

```bash
python3 -m pytest tests/ -v
cd frontend && npx jest --verbose && npm run build
```
Expected: todos passam

**Step 2: Deploy backend**

```bash
func azure functionapp publish az-pg-spend-analysis-ai-agent --python
```

**Step 3: Deploy frontend**

Push para `main` → GitHub Actions faz deploy automático.

```bash
git push origin main
```

**Step 4: Validação manual**

Checklist:
- [ ] Upload Excel com coluna "Fornecedor" → classificar → revisar → coluna "Fornecedor" visível na tabela
- [ ] Upload Excel SEM colunas extras → revisar → tabela funciona normalmente (backward compat)
- [ ] Finalizar revisão → aba Analisar → chat limpo, executive summary gerado
- [ ] Botão "Limpar Chat" (ícone lixeira) aparece quando há mensagens e funciona
- [ ] Trocar de sessão → chat carrega dados da nova sessão (ou vazio se nova)
- [ ] Itens não classificados mostram "Não Identificado" no Excel baixado
- [ ] Coluna "Fonte" mostra "Ajuste Manual" para itens editados
- [ ] Sessões antigas do IndexedDB (sem extraColumns) carregam sem erro
