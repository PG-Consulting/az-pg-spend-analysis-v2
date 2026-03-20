# Web Search Toggle — Plano de Implementação

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Adicionar toggle "Busca na Internet" no ClassifyTab para que o Grok use web_search ao classificar itens.

**Architecture:** Um campo booleano `use_web_search` percorre o pipeline: ClassifyTab → API client → SubmitTaxonomyJob → status.json → Worker → core_classification → llm_classifier. Quando true, adiciona `"tools": [{"type": "web_search"}]` ao payload e instrução de busca ao prompt.

**Tech Stack:** Next.js/React (frontend), Azure Functions/Python (backend), xAI Grok API (web_search tool)

---

### Task 1: Backend — `llm_classifier.py` (parâmetro + payload + prompt)

**Files:**
- Modify: `src/llm_classifier.py:76-83` (assinatura `classify_items_with_llm`)
- Modify: `src/llm_classifier.py:122-130` (submit para `_call_openai_api`)
- Modify: `src/llm_classifier.py:173-181` (assinatura `_call_openai_api`)
- Modify: `src/llm_classifier.py:236-256` (instrução web search no prompt)
- Modify: `src/llm_classifier.py:260-267` (payload tools)

**Step 1: Adicionar `use_web_search` a `classify_items_with_llm`**

Na assinatura (linha 76-83), adicionar parâmetro:

```python
def classify_items_with_llm(
    descriptions: List[str],
    sector: str = "Padrão",
    client_context: str = "",
    custom_hierarchy: Optional[Union[Dict[str, HierarchyEntryDict], List[HierarchyEntryDict]]] = None,
    few_shot_examples: Optional[List[KBEntryDict]] = None,
    user_instruction: Optional[str] = None,
    use_web_search: bool = False,
) -> List[ClassificationResultDict]:
```

No `executor.submit` (linha 122-130), passar o novo param:

```python
executor.submit(
    _call_openai_api,
    chunk_items, config, sector, client_context, custom_hierarchy,
    few_shot_examples, user_instruction, use_web_search
)
```

**Step 2: Adicionar `use_web_search` a `_call_openai_api`**

Na assinatura (linha 173-181):

```python
def _call_openai_api(
    items: List[str],
    config: Dict[str, str],
    sector: str = "Padrão",
    client_context: str = "",
    custom_hierarchy: Optional[Union[Dict[str, HierarchyEntryDict], List[HierarchyEntryDict]]] = None,
    few_shot_examples: Optional[List[KBEntryDict]] = None,
    user_instruction: Optional[str] = None,
    use_web_search: bool = False,
) -> List[ClassificationResultDict]:
```

**Step 3: Adicionar instrução de busca web ao prompt**

Após o bloco de `user_instruction` (após linha 256), adicionar:

```python
    # Add web search instruction if enabled
    if use_web_search:
        system_message += (
            "\n\nBUSCA NA INTERNET (HABILITADA):\n"
            "Você tem acesso à internet. Para itens com descrições ambíguas, "
            "códigos, siglas, nomes de fornecedores, fabricantes ou marcas "
            "que você não reconhece com certeza:\n"
            "- Pesquise na web o que o fornecedor/fabricante produz\n"
            "- Pesquise o que o produto/material/serviço é\n"
            "- Use essa informação para escolher a categoria mais precisa\n\n"
            "Mantenha o formato de saída JSON idêntico."
        )
```

**Step 4: Adicionar `tools` ao payload**

Após montar o payload (linha 260-267), adicionar:

```python
    payload = {
        "model": config["deployment"],
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0,
    }

    if use_web_search:
        payload["tools"] = [{"type": "web_search"}]
```

**Step 5: Rodar testes existentes**

Run: `python3 -m pytest tests/test_core_classification.py -v`
Expected: PASS — nenhum teste existente deve quebrar (default `use_web_search=False`)

**Step 6: Commit**

```bash
git add src/llm_classifier.py
git commit -m "Adicionando suporte a web_search no llm_classifier (param + payload + prompt)"
```

---

### Task 2: Backend — `core_classification.py` (propagação)

**Files:**
- Modify: `src/core_classification.py:24-37` (assinatura `process_dataframe_chunk`)
- Modify: `src/core_classification.py:55-59` (chamada `_llm_direct_pipeline`)
- Modify: `src/core_classification.py:64-72` (assinatura `_llm_direct_pipeline`)
- Modify: `src/core_classification.py:143-150` (chamada `classify_items_with_llm`)

**Step 1: Adicionar `use_web_search` a `process_dataframe_chunk`**

```python
def process_dataframe_chunk(
    df_chunk: pd.DataFrame,
    desc_column: str,
    sector: str = "Padrão",
    models_dir: Optional[str] = None,
    custom_hierarchy: Optional[List[HierarchyEntryDict]] = None,
    client_context: str = "",
    few_shot_examples: Optional[List[KBEntryDict]] = None,
    hierarchy_lookup: Optional[object] = None,
    use_legacy_ml: bool = False,
    project_id: Optional[str] = None,
    user_instruction: Optional[str] = None,
    kb_retriever: Optional[object] = None,
    use_web_search: bool = False,
) -> List[ClassificationResultDict]:
```

**Step 2: Propagar para `_llm_direct_pipeline`**

```python
    results = _llm_direct_pipeline(
        descriptions, sector, client_context, custom_hierarchy,
        few_shot_examples, hierarchy_lookup, user_instruction,
        kb_retriever=kb_retriever,
        use_web_search=use_web_search,
    )
```

**Step 3: Adicionar `use_web_search` a `_llm_direct_pipeline`**

```python
def _llm_direct_pipeline(
    descriptions: List[str],
    sector: str,
    client_context: str,
    custom_hierarchy: Optional[List[HierarchyEntryDict]],
    few_shot_examples: Optional[List[KBEntryDict]],
    hierarchy_lookup: Optional[object],
    user_instruction: Optional[str] = None,
    kb_retriever: Optional[object] = None,
    use_web_search: bool = False,
) -> List[ClassificationResultDict]:
```

**Step 4: Propagar para `classify_items_with_llm`**

```python
        llm_results = classify_items_with_llm(
            remaining_descs,
            sector=sector or "Padrão",
            client_context=client_context,
            custom_hierarchy=custom_hierarchy,
            few_shot_examples=enriched_examples,
            user_instruction=user_instruction,
            use_web_search=use_web_search,
        )
```

**Step 5: Rodar testes**

Run: `python3 -m pytest tests/test_core_classification.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/core_classification.py
git commit -m "Propagando use_web_search por core_classification → llm_classifier"
```

---

### Task 3: Backend — `worker_helpers.py` (lê flag do job)

**Files:**
- Modify: `src/worker_helpers.py:260-307` (`process_single_chunk`)

**Step 1: Ler `use_web_search` do status e passar para `process_dataframe_chunk`**

Em `process_single_chunk`, após a linha `desc_col = status.get(...)` (linha 291), adicionar:

```python
    use_web_search = status.get("use_web_search", False)
```

Na chamada `process_dataframe_chunk` (linha 295-307), adicionar o param:

```python
    results = process_dataframe_chunk(
        df_chunk,
        desc_column=desc_col,
        sector=sector,
        models_dir=models_dir,
        custom_hierarchy=custom_hierarchy,
        client_context=client_context,
        few_shot_examples=kb_entries if kb_entries else None,
        hierarchy_lookup=hierarchy_lookup,
        use_legacy_ml=(not project_id),
        project_id=project_id,
        kb_retriever=kb_retriever,
        use_web_search=use_web_search,
    )
```

**Step 2: Rodar testes**

Run: `python3 -m pytest tests/ -v -k "worker"`
Expected: PASS

**Step 3: Commit**

```bash
git add src/worker_helpers.py
git commit -m "Worker lê use_web_search do job e propaga ao classificador"
```

---

### Task 4: Backend — `classification_bp.py` (recebe e salva flag)

**Files:**
- Modify: `blueprints/classification_bp.py:186-210` (metadata do SubmitTaxonomyJob)

**Step 1: Ler `useWebSearch` do body e salvar no metadata**

Após `"project_id": project_id or None,` (linha 201), adicionar:

```python
        "use_web_search": bool(req_body.get("useWebSearch", False)),
```

**Step 2: Rodar testes**

Run: `python3 -m pytest tests/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add blueprints/classification_bp.py
git commit -m "SubmitTaxonomyJob aceita useWebSearch e salva no status.json"
```

---

### Task 5: Backend — Testes unitários

**Files:**
- Modify: `tests/test_core_classification.py` (adicionar 3 testes)

**Step 1: Escrever testes**

Adicionar ao final de `tests/test_core_classification.py`:

```python
# ---------------------------------------------------------------------------
# Web Search toggle tests
# ---------------------------------------------------------------------------

class TestWebSearchToggle:
    """Test use_web_search parameter propagation."""

    @patch("src.llm_classifier.requests.post")
    def test_web_search_adds_tools_to_payload(self, mock_post):
        """When use_web_search=True, payload must include tools."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '[{"item": "x", "N1": "A", "N2": "B", "N3": "C", "N4": "D", "confidence": 0.9}]'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_post.return_value = mock_response

        from src.llm_classifier import classify_items_with_llm
        classify_items_with_llm(["item test"], use_web_search=True)

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "tools" in payload, "Payload should include 'tools' when use_web_search=True"
        assert payload["tools"] == [{"type": "web_search"}]

    @patch("src.llm_classifier.requests.post")
    def test_no_web_search_by_default(self, mock_post):
        """When use_web_search is not set, payload must NOT include tools."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '[{"item": "x", "N1": "A", "N2": "B", "N3": "C", "N4": "D", "confidence": 0.9}]'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_post.return_value = mock_response

        from src.llm_classifier import classify_items_with_llm
        classify_items_with_llm(["item test"])

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "tools" not in payload, "Payload should NOT include 'tools' by default"

    @patch("src.llm_classifier.requests.post")
    def test_web_search_adds_prompt_instruction(self, mock_post):
        """When use_web_search=True, system message must include search instruction."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '[{"item": "x", "N1": "A", "N2": "B", "N3": "C", "N4": "D", "confidence": 0.9}]'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_post.return_value = mock_response

        from src.llm_classifier import classify_items_with_llm
        classify_items_with_llm(["item test"], use_web_search=True)

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        system_msg = payload["messages"][0]["content"]
        assert "BUSCA NA INTERNET" in system_msg
        assert "Pesquise na web" in system_msg
```

**Step 2: Rodar testes**

Run: `python3 -m pytest tests/test_core_classification.py::TestWebSearchToggle -v`
Expected: PASS (3 testes)

**Step 3: Rodar suite completa**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (todos ~200 testes)

**Step 4: Commit**

```bash
git add tests/test_core_classification.py
git commit -m "Adicionando testes para toggle web_search (payload, prompt, default)"
```

---

### Task 6: Frontend — `api.ts` (novo parâmetro)

**Files:**
- Modify: `frontend/src/lib/api.ts:345-374` (`submitClassificationJobRaw`)

**Step 1: Adicionar `useWebSearch` ao params e body**

```typescript
  async submitClassificationJobRaw(params: {
    fileContent: string;
    originalFilename: string;
    projectId?: string;
    sector?: string;
    descColumn?: string;
    customHierarchy?: string;
    clientContext?: string;
    useWebSearch?: boolean;
  }): Promise<{ jobId: string }> {
    const requestBody: Record<string, unknown> = {
      fileContent: params.fileContent,
      originalFilename: params.originalFilename,
    };

    if (params.projectId) requestBody.projectId = params.projectId;
    if (params.sector) requestBody.sector = params.sector;
    if (params.descColumn) requestBody.descColumn = params.descColumn;
    if (params.customHierarchy) requestBody.customHierarchy = params.customHierarchy;
    if (params.clientContext) requestBody.clientContext = params.clientContext;
    if (params.useWebSearch) requestBody.useWebSearch = true;
```

**Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "API client aceita useWebSearch em submitClassificationJobRaw"
```

---

### Task 7: Frontend — `useTaxonomySession.ts` (propaga flag)

**Files:**
- Modify: `frontend/src/hooks/useTaxonomySession.ts:34` (assinatura `handleFileSelect`)
- Modify: `frontend/src/hooks/useTaxonomySession.ts:81-98` (implementação)

**Step 1: Adicionar `useWebSearch` ao `handleFileSelect`**

Atualizar assinatura (linha 81-85):

```typescript
    const handleFileSelect = async (
        file: File,
        fileContent: string,
        hierarchyContent?: string,
        useWebSearch?: boolean
    ) => {
```

Atualizar a chamada ao `submitClassificationJobRaw` (linha 93-98):

```typescript
            const { jobId } = await apiClient.submitClassificationJobRaw({
                fileContent,
                originalFilename: file.name,
                projectId: activeProjectId || undefined,
                customHierarchy: hierarchyContent,
                useWebSearch,
            })
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useTaxonomySession.ts
git commit -m "useTaxonomySession propaga useWebSearch ao submeter job"
```

---

### Task 8: Frontend — `ClassifyTab.tsx` (toggle UI)

**Files:**
- Modify: `frontend/src/components/taxonomy/ClassifyTab.tsx`

**Step 1: Atualizar interface e callback**

Atualizar `ClassifyTabProps` (linha 5-10):

```typescript
interface ClassifyTabProps {
  onFileSelect: (file: File, fileContent: string, hierarchyContent?: string, useWebSearch?: boolean) => void
  isProcessing: boolean
  projectId?: string | null
  projectHierarchy?: any[] | null
}
```

**Step 2: Adicionar state para web search**

Após `const [hierarchyOpen, setHierarchyOpen] = useState(false)` (linha 20), adicionar:

```typescript
  const [useWebSearch, setUseWebSearch] = useState(false)
```

**Step 3: Atualizar handleSubmit para passar flag**

Atualizar `handleSubmit` (linha 85-93):

```typescript
  const handleSubmit = () => {
    if (baseValidation?.isValid) {
      onFileSelect(
        baseValidation.file,
        baseValidation.content,
        hierarchyValidation?.isValid ? hierarchyValidation.content : undefined,
        useWebSearch
      )
    }
  }
```

**Step 4: Adicionar toggle na UI**

Antes do `{/* ── CTA Button ── */}` (linha 167), adicionar:

```tsx
      {/* ── Web Search Toggle ── */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 rounded-xl">
        <div className="flex items-center gap-2.5">
          <svg className="w-4 h-4 text-accent-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <div>
            <span className="text-sm font-medium text-gray-700">Busca na Internet</span>
            <p className="text-[11px] text-gray-400 mt-0.5">
              O Grok pesquisa na web sobre cada item para classificar com mais contexto
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setUseWebSearch(prev => !prev)}
          disabled={isProcessing}
          className={[
            'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-accent-500/20',
            useWebSearch ? 'bg-accent-500' : 'bg-gray-200',
            isProcessing && 'opacity-50 cursor-not-allowed',
          ].join(' ')}
        >
          <span
            className={[
              'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
              useWebSearch ? 'translate-x-4' : 'translate-x-0',
            ].join(' ')}
          />
        </button>
      </div>
```

**Step 5: Rodar testes frontend**

Run: `cd frontend && npx jest --verbose`
Expected: PASS

**Step 6: Commit**

```bash
git add frontend/src/components/taxonomy/ClassifyTab.tsx
git commit -m "Adicionando toggle 'Busca na Internet' no ClassifyTab"
```

---

### Task 9: Verificação final

**Step 1: Rodar testes backend**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (~200 testes)

**Step 2: Rodar testes frontend**

Run: `cd frontend && npx jest --verbose`
Expected: PASS (~48 testes)

**Step 3: Verificar build frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: sem erros de tipo

**Step 4: Commit final (se necessário)**

Se houve ajustes durante verificação.
