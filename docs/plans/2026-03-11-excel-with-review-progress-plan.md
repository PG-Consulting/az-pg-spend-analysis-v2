# Excel com Progresso de Revisão — Plano de Implementação

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir download do Excel com as alterações feitas na tela de revisão sem finalizar o job.

**Architecture:** Estender `DownloadJobExcel` para aceitar POST com decisions parciais. O backend mescla decisions com `result.json`, adiciona coluna "Status", e retorna Excel. GET mantém comportamento atual.

**Tech Stack:** Python (Azure Functions, pandas, openpyxl), TypeScript (Next.js, axios)

**Spec:** `docs/plans/2026-03-11-excel-with-review-progress-design.md`

---

## Chunk 1: Backend — Testes e Implementação

### Task 1: Testes backend para POST com decisions

**Files:**
- Modify: `tests/test_download_job_excel.py`

- [ ] **Step 1: Adicionar helper `_generate_excel_with_decisions`**

Adicionar ao topo do arquivo (após `_generate_excel_from_items`):

```python
def _generate_excel_with_decisions(items, decisions=None, id_col=None, extra_columns=None):
    """Reproduce the POST Excel generation logic with decisions merge."""
    decision_map = {}
    if decisions:
        for d in decisions:
            decision_map[d["index"]] = d

    rows = []
    for idx, item in enumerate(items):
        d = decision_map.get(idx)
        row = {}
        if id_col:
            row[id_col] = item.get(id_col, "")
        row["Descricao"] = item.get("Descricao", item.get("description", ""))
        if extra_columns:
            for col in extra_columns:
                row[col] = item.get(col, "")

        if d and d["decision"] == "edited":
            row["N1"] = d.get("N1", "")
            row["N2"] = d.get("N2", "")
            row["N3"] = d.get("N3", "")
            row["N4"] = d.get("N4", "")
            row["Fonte"] = "Ajuste Manual"
        else:
            row["N1"] = item.get("N1", "")
            row["N2"] = item.get("N2", "")
            row["N3"] = item.get("N3", "")
            row["N4"] = item.get("N4", "")
            row["Fonte"] = item.get("source", "")

        if decisions is not None:
            if d:
                status_map = {"approved": "Aprovado", "edited": "Editado", "rejected": "Rejeitado"}
                row["Status"] = status_map.get(d["decision"], "Pendente")
            else:
                row["Status"] = "Pendente"

        rows.append(row)

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Resultados", engine="openpyxl")
    return buf.getvalue()
```

- [ ] **Step 2: Adicionar testes para POST com decisions**

Adicionar à classe `TestDownloadJobExcel`:

```python
    def test_post_empty_decisions_adds_status_column_all_pending(self, tmp_path):
        """POST with empty decisions list adds Status column with all Pendente."""
        items = [
            {"Descricao": "Parafuso M8", "N1": "Materiais", "N2": "Fixadores",
             "N3": "Parafusos", "N4": "Parafuso M8", "source": "Grok", "confidence": 0.92},
        ]
        excel_bytes = _generate_excel_with_decisions(items, decisions=[])
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert "Status" in df.columns
        assert list(df.columns) == ["Descricao", "N1", "N2", "N3", "N4", "Fonte", "Status"]
        assert df.iloc[0]["Status"] == "Pendente"

    def test_post_mix_decisions_merge_correctly(self, tmp_path):
        """POST with mixed decisions merges N1-N4, Fonte, Status correctly."""
        items = [
            {"Descricao": "Item A", "N1": "Cat1", "N2": "Sub1",
             "N3": "Grp1", "N4": "Det1", "source": "Grok", "confidence": 0.9},
            {"Descricao": "Item B", "N1": "Cat2", "N2": "Sub2",
             "N3": "Grp2", "N4": "Det2", "source": "Base de Aprendizado", "confidence": 0.95},
            {"Descricao": "Item C", "N1": "Cat3", "N2": "Sub3",
             "N3": "Grp3", "N4": "Det3", "source": "Grok", "confidence": 0.5},
        ]
        decisions = [
            {"index": 0, "decision": "approved", "N1": "Cat1", "N2": "Sub1", "N3": "Grp1", "N4": "Det1"},
            {"index": 2, "decision": "edited", "N1": "CatX", "N2": "SubX", "N3": "GrpX", "N4": "DetX"},
        ]
        excel_bytes = _generate_excel_with_decisions(items, decisions=decisions)
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")

        # Item 0: approved — N1-N4 do pipeline, Fonte do pipeline, Status Aprovado
        assert df.iloc[0]["N4"] == "Det1"
        assert df.iloc[0]["Fonte"] == "Grok"
        assert df.iloc[0]["Status"] == "Aprovado"

        # Item 1: sem decision — Pendente
        assert df.iloc[1]["N4"] == "Det2"
        assert df.iloc[1]["Fonte"] == "Base de Aprendizado"
        assert df.iloc[1]["Status"] == "Pendente"

        # Item 2: edited — N1-N4 da decision, Fonte "Ajuste Manual", Status Editado
        assert df.iloc[2]["N4"] == "DetX"
        assert df.iloc[2]["Fonte"] == "Ajuste Manual"
        assert df.iloc[2]["Status"] == "Editado"

    def test_post_rejected_item_included_with_status(self, tmp_path):
        """POST with rejected item includes it in Excel with Status=Rejeitado."""
        items = [
            {"Descricao": "Item A", "N1": "Cat1", "N2": "Sub1",
             "N3": "Grp1", "N4": "Det1", "source": "Grok", "confidence": 0.9},
        ]
        decisions = [
            {"index": 0, "decision": "rejected", "N1": "Cat1", "N2": "Sub1", "N3": "Grp1", "N4": "Det1"},
        ]
        excel_bytes = _generate_excel_with_decisions(items, decisions=decisions)
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert len(df) == 1  # não exclui rejeitados
        assert df.iloc[0]["Status"] == "Rejeitado"
        assert df.iloc[0]["N4"] == "Det1"  # mantém N1-N4 do pipeline

    def test_get_without_decisions_no_status_column(self, tmp_path):
        """GET (no decisions) should NOT have Status column — backward compat."""
        items = [
            {"Descricao": "Parafuso M8", "N1": "Materiais", "N2": "Fixadores",
             "N3": "Parafusos", "N4": "Parafuso M8", "source": "LLM (Batch)", "confidence": 0.92},
        ]
        excel_bytes = _generate_excel_from_items(items)
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert "Status" not in df.columns

    def test_post_with_extra_columns_and_decisions(self, tmp_path):
        """POST with extra_columns + decisions preserves all columns correctly."""
        items = [
            {"Descricao": "Parafuso M8", "Fornecedor": "ABC Ltda", "N1": "Materiais",
             "N2": "Fixadores", "N3": "Parafusos", "N4": "Parafuso M8",
             "source": "Grok", "confidence": 0.92},
        ]
        decisions = [
            {"index": 0, "decision": "edited", "N1": "Materiais", "N2": "Fixadores",
             "N3": "Parafusos", "N4": "Parafuso M10"},
        ]
        excel_bytes = _generate_excel_with_decisions(
            items, decisions=decisions, extra_columns=["Fornecedor"]
        )
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert list(df.columns) == ["Descricao", "Fornecedor", "N1", "N2", "N3", "N4", "Fonte", "Status"]
        assert df.iloc[0]["Fornecedor"] == "ABC Ltda"
        assert df.iloc[0]["N4"] == "Parafuso M10"
        assert df.iloc[0]["Fonte"] == "Ajuste Manual"
        assert df.iloc[0]["Status"] == "Editado"
```

- [ ] **Step 3: Rodar testes para verificar que passam**

Run: `python3 -m pytest tests/test_download_job_excel.py -v`
Expected: Todos passam (10 testes: 5 existentes + 5 novos)

- [ ] **Step 4: Commit**

```bash
git add tests/test_download_job_excel.py
git commit -m "Adicionando testes para DownloadJobExcel POST com decisions"
```

---

### Task 2: Implementar POST no DownloadJobExcel

**Files:**
- Modify: `blueprints/classification_bp.py:478-562`

- [ ] **Step 1: Atualizar route decorator e OPTIONS**

Em `classification_bp.py`, alterar linhas 478-495:

```python
@classification_bp.route(
    route="DownloadJobExcel",
    methods=["GET", "POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("DownloadJobExcel")
@require_auth
def DownloadJobExcel(req: func.HttpRequest) -> func.HttpResponse:
    """GET/POST /api/DownloadJobExcel?jobId=xxx
    GET: Returns raw classified results as Excel.
    POST: Merges review decisions into results, adds Status column.
    Only works for CLASSIFIED, APPROVED, or COMPLETED jobs.
    """
    import pandas as pd

    if req.method == "OPTIONS":
        return options_response(req, "GET, POST, OPTIONS")
```

- [ ] **Step 2: Adicionar parse de decisions após carregar result.json**

Após a linha `raw_items = result_json.get("items", [])` (atual linha 527), adicionar:

```python
    # Parse decisions from POST body (if present)
    decisions = None
    decision_map = {}
    if req.method == "POST":
        try:
            body = req.get_json()
            decisions = body.get("decisions", [])
        except (ValueError, AttributeError):
            decisions = []

        # Validate decisions
        valid_decisions = ("approved", "edited", "rejected")
        if len(decisions) > len(raw_items):
            raise ValidationError(
                f"Mais decisions ({len(decisions)}) que itens ({len(raw_items)})."
            )
        for d in decisions:
            idx = d.get("index")
            dec = d.get("decision")
            if not isinstance(idx, int) or idx < 0 or idx >= len(raw_items):
                raise ValidationError(
                    f"Decision index inválido: {idx} (total itens: {len(raw_items)})"
                )
            if dec not in valid_decisions:
                raise ValidationError(
                    f"Decision inválida: '{dec}'. Esperado: {valid_decisions}"
                )
            decision_map[idx] = d  # último ganha em caso de duplicata
```

- [ ] **Step 3: Substituir o loop de geração de rows**

Substituir o loop existente (linhas 529-542) por:

```python
    _STATUS_LABELS = {
        "approved": "Aprovado",
        "edited": "Editado",
        "rejected": "Rejeitado",
    }

    rows = []
    for idx, item in enumerate(raw_items):
        row = {}
        if id_col:
            row[id_col] = item.get(id_col, "")
        row["Descricao"] = item.get(desc_col, item.get("description", ""))
        for col in extra_columns:
            row[col] = item.get(col, "")

        d = decision_map.get(idx)
        if d and d["decision"] == "edited":
            row["N1"] = d.get("N1", "")
            row["N2"] = d.get("N2", "")
            row["N3"] = d.get("N3", "")
            row["N4"] = d.get("N4", "")
            row["Fonte"] = "Ajuste Manual"
        else:
            row["N1"] = item.get("N1", "")
            row["N2"] = item.get("N2", "")
            row["N3"] = item.get("N3", "")
            row["N4"] = item.get("N4", "")
            if decisions is not None:
                # POST: result.json já tem labels amigáveis — usar direto
                row["Fonte"] = item.get("source", "")
            else:
                # GET: backward compat — chama friendly_source_label
                row["Fonte"] = friendly_source_label(item.get("source", ""))

        # Coluna Status só no POST
        if decisions is not None:
            if d:
                row["Status"] = _STATUS_LABELS.get(d["decision"], "Pendente")
            else:
                row["Status"] = "Pendente"

        rows.append(row)
```

- [ ] **Step 4: Rodar todos os testes do backend**

Run: `python3 -m pytest tests/test_download_job_excel.py -v`
Expected: Todos passam (10 testes)

Run: `python3 -m pytest tests/ -v --timeout=30`
Expected: Todos os 272+ testes passam (nenhum teste existente quebrado)

- [ ] **Step 5: Commit**

```bash
git add blueprints/classification_bp.py
git commit -m "Adicionando POST com decisions no DownloadJobExcel — merge + coluna Status"
```

---

## Chunk 2: Frontend — API client e ReviewTab

### Task 3: Atualizar api.ts para suportar POST com decisions

**Files:**
- Modify: `frontend/src/lib/api.ts:463-470`

- [ ] **Step 1: Definir tipo Decision**

Em `api.ts`, adicionar o tipo antes do método `downloadJobExcel` (ou em `types.ts` se preferir — mas como é usado apenas aqui, manter local):

Na assinatura do método, alterar de:

```typescript
  /** Downloads raw classification results as Excel (before review). */
  async downloadJobExcel(jobId: string): Promise<{ filename: string; file_content_base64: string }> {
    const response = await axios.get(`${API_BASE_URL}/DownloadJobExcel`, {
      params: { jobId },
      headers: await getAuthHeaders(),
    });
    return response.data;
  },
```

Para:

```typescript
  /** Downloads classification results as Excel. POST with decisions includes review progress. */
  async downloadJobExcel(
    jobId: string,
    decisions?: Array<{ index: number; decision: string; N1: string; N2: string; N3: string; N4: string }>
  ): Promise<{ filename: string; file_content_base64: string }> {
    if (decisions && decisions.length > 0) {
      const response = await axios.post(
        `${API_BASE_URL}/DownloadJobExcel`,
        { decisions },
        { params: { jobId }, headers: await getAuthHeaders() }
      );
      return response.data;
    }
    const response = await axios.get(`${API_BASE_URL}/DownloadJobExcel`, {
      params: { jobId },
      headers: await getAuthHeaders(),
    });
    return response.data;
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "Adicionando suporte a POST com decisions no downloadJobExcel"
```

---

### Task 4: Atualizar ReviewTab para enviar decisions no download

**Files:**
- Modify: `frontend/src/components/taxonomy/ReviewTab.tsx:157-168`

- [ ] **Step 1: Alterar `handleDownloadAsIs`**

Substituir o bloco `handleDownloadAsIs` (linhas 157-168) por:

```typescript
  const handleDownloadAsIs = async () => {
    setIsDownloading(true);
    try {
      const api = await import('../../lib/api').then(m => m.apiClient);

      // Coletar decisions do estado de revisão
      const decisions: Array<{ index: number; decision: string; N1: string; N2: string; N3: string; N4: string }> = [];
      for (const item of localItems) {
        const state = getItemState(item.index);
        if (state.decision && state.decision !== 'pending') {
          decisions.push({
            index: item.index,
            decision: state.decision,
            N1: state.decision === 'edited' ? (state.editedN1 || item.N1) : item.N1,
            N2: state.decision === 'edited' ? (state.editedN2 || item.N2) : item.N2,
            N3: state.decision === 'edited' ? (state.editedN3 || item.N3) : item.N3,
            N4: state.decision === 'edited' ? (state.editedN4 || item.N4) : item.N4,
          });
        }
      }

      const result = await api.downloadJobExcel(jobId, decisions);
      downloadBase64AsFile(result.file_content_base64, result.filename);
    } catch (e) {
      console.error('Download failed:', e);
    } finally {
      setIsDownloading(false);
    }
  };
```

- [ ] **Step 2: Atualizar tooltip do botão**

Em `ReviewTab.tsx` linha 246, alterar o `title` do botão:

De: `title="Baixar Excel com resultado bruto da classificação"`
Para: `title="Baixar Excel com progresso da revisão"`

- [ ] **Step 3: Verificar build TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: Sem erros de tipo

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/taxonomy/ReviewTab.tsx
git commit -m "Adicionando envio de decisions no download Excel do ReviewTab"
```

---

### Task 5: Testes frontend

**Files:**
- Modify: `frontend/src/__tests__/api.test.ts`

- [ ] **Step 1: Adicionar testes para downloadJobExcel**

Adicionar bloco de testes ao final do arquivo:

Usar o padrão `mockedAxios` existente no arquivo de testes (não `axios.get as jest.Mock`):

```typescript
describe('downloadJobExcel', () => {
  it('sends GET when no decisions provided', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValueOnce({
      data: { filename: 'test_resultado.xlsx', file_content_base64: 'abc123' },
    });

    const result = await apiClient.downloadJobExcel('job-1');

    expect(mockedAxios.get).toHaveBeenCalledWith(
      expect.stringContaining('/DownloadJobExcel'),
      expect.objectContaining({ params: { jobId: 'job-1' } })
    );
    expect(result.filename).toBe('test_resultado.xlsx');
  });

  it('sends POST when decisions provided', async () => {
    const decisions = [
      { index: 0, decision: 'approved', N1: 'A', N2: 'B', N3: 'C', N4: 'D' },
      { index: 2, decision: 'edited', N1: 'X', N2: 'Y', N3: 'Z', N4: 'W' },
    ];

    (mockedAxios.post as jest.Mock).mockResolvedValueOnce({
      data: { filename: 'test_resultado.xlsx', file_content_base64: 'xyz789' },
    });

    const result = await apiClient.downloadJobExcel('job-1', decisions);

    expect(mockedAxios.post).toHaveBeenCalledWith(
      expect.stringContaining('/DownloadJobExcel'),
      { decisions },
      expect.objectContaining({ params: { jobId: 'job-1' } })
    );
    expect(result.file_content_base64).toBe('xyz789');
  });

  it('sends GET when decisions is empty array', async () => {
    (mockedAxios.get as jest.Mock).mockResolvedValueOnce({
      data: { filename: 'test_resultado.xlsx', file_content_base64: 'abc' },
    });

    await apiClient.downloadJobExcel('job-1', []);

    expect(mockedAxios.get).toHaveBeenCalled();
    expect(mockedAxios.post).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Rodar testes frontend**

Run: `cd frontend && npx jest --verbose`
Expected: Todos os 53+ testes passam

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/api.test.ts
git commit -m "Adicionando testes para downloadJobExcel com decisions"
```

---

## Chunk 3: Validação final

### Task 6: Rodar todos os testes e verificar

- [ ] **Step 1: Testes backend completos**

Run: `python3 -m pytest tests/ -v`
Expected: 272+ testes passam (267 existentes + 5 novos)

- [ ] **Step 2: Testes frontend completos**

Run: `cd frontend && npx jest --verbose`
Expected: 53+ testes passam (50 existentes + 3 novos)

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build sem erros

- [ ] **Step 4: Commit final (se houver ajustes)**

Apenas se necessário para corrigir algo encontrado na validação.
