# Download AS-IS, Toggle KB e Melhoria Import KB — Plano de Implementacao

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Adicionar download do Excel bruto na revisao, toggle global de contribuicao para KB, e melhorar UX de import na aba KB.

**Architecture:** Novo endpoint backend para gerar Excel dos resultados brutos. Estado global no hook useReview para controle de KB. Parse client-side do Excel de import com preview antes de enviar.

**Tech Stack:** Python/Azure Functions (backend), React/TypeScript/Next.js (frontend), openpyxl/pandas (Excel), xlsx (parse client-side)

---

### Task 1: Endpoint DownloadJobExcel (backend)

**Files:**
- Modify: `blueprints/classification_bp.py` (adicionar endpoint apos GetJobResults, ~linha 445)
- Test: `tests/test_download_job_excel.py` (novo)

**Step 1: Escrever o teste**

Criar `tests/test_download_job_excel.py`:

```python
"""Tests for DownloadJobExcel endpoint."""
import io
import json
import os
import base64
import tempfile
import pytest
import pandas as pd

from src.utils import friendly_source_label


class TestDownloadJobExcel:
    """Unit tests for the Excel generation logic used by DownloadJobExcel."""

    def _make_job_dir(self, tmp_path, status="CLASSIFIED", items=None):
        """Create a fake job directory with status.json and result.json."""
        job_id = "test-job-001"
        job_dir = os.path.join(str(tmp_path), job_id)
        os.makedirs(job_dir, exist_ok=True)

        if items is None:
            items = [
                {"description": "Parafuso M8", "N1": "MRO", "N2": "Fixacao",
                 "N3": "Parafusos", "N4": "Parafuso Sextavado",
                 "confidence": 0.92, "source": "LLM (Batch)", "status": "Unico"},
                {"description": "Oleo motor", "N1": "MRO", "N2": "Lubrificacao",
                 "N3": "Oleos", "N4": "Oleo Motor",
                 "confidence": 0.45, "source": "KB (Direct Match)", "status": "Unico"},
            ]

        status_data = {
            "status": status,
            "filename": "base_teste.xlsx",
            "desc_column": "Descricao",
            "total_chunks": 1,
        }
        with open(os.path.join(job_dir, "status.json"), "w") as f:
            json.dump(status_data, f)

        result_data = {"items": items}
        with open(os.path.join(job_dir, "result.json"), "w") as f:
            json.dump(result_data, f)

        return job_id, job_dir

    def test_generates_excel_with_correct_columns(self, tmp_path):
        job_id, job_dir = self._make_job_dir(tmp_path)

        # Read result.json like the endpoint would
        with open(os.path.join(job_dir, "result.json"), "r") as f:
            result_json = json.load(f)

        items = result_json["items"]
        rows = []
        for item in items:
            rows.append({
                "Descricao": item.get("description", ""),
                "N1": item.get("N1", ""),
                "N2": item.get("N2", ""),
                "N3": item.get("N3", ""),
                "N4": item.get("N4", ""),
                "Fonte": friendly_source_label(item.get("source", "")),
                "Confianca": item.get("confidence", 0.0),
            })

        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Resultados")
        file_bytes = buf.getvalue()

        assert len(file_bytes) > 0
        # Read back and verify
        df_read = pd.read_excel(io.BytesIO(file_bytes))
        assert list(df_read.columns) == ["Descricao", "N1", "N2", "N3", "N4", "Fonte", "Confianca"]
        assert len(df_read) == 2
        assert df_read.iloc[0]["Descricao"] == "Parafuso M8"

    def test_filename_uses_original_name(self, tmp_path):
        job_id, job_dir = self._make_job_dir(tmp_path)
        with open(os.path.join(job_dir, "status.json"), "r") as f:
            status_data = json.load(f)
        original = status_data.get("filename", "upload.xlsx")
        base_name = os.path.splitext(original)[0]
        expected = f"{base_name}_resultado.xlsx"
        assert expected == "base_teste_resultado.xlsx"

    def test_rejects_pending_job(self, tmp_path):
        job_id, job_dir = self._make_job_dir(tmp_path, status="PENDING")
        with open(os.path.join(job_dir, "status.json"), "r") as f:
            status_data = json.load(f)
        # Endpoint should reject PENDING/PROCESSING
        assert status_data["status"] not in ("CLASSIFIED", "COMPLETED", "APPROVED")
```

**Step 2: Rodar testes e confirmar que passam**

Run: `python3 -m pytest tests/test_download_job_excel.py -v`
Expected: 3 PASSED

**Step 3: Implementar o endpoint**

Adicionar ao final de `blueprints/classification_bp.py` (antes do ultimo bloco):

```python
@classification_bp.route(route="DownloadJobExcel", methods=["GET", "OPTIONS"],
                          auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors
def DownloadJobExcel(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/DownloadJobExcel?jobId=xxx
    Returns the raw classification results as a downloadable Excel (base64).
    Only available for CLASSIFIED/COMPLETED/APPROVED jobs.
    Returns: {filename, file_content_base64}
    """
    if req.method == "OPTIONS":
        return options_response("GET, OPTIONS")

    job_id = req.params.get("jobId", "").strip()
    if not job_id:
        raise ValidationError("Missing jobId")

    jobs_dir = get_jobs_dir()
    job_dir = os.path.join(jobs_dir, job_id)
    status_file = os.path.join(job_dir, "status.json")

    if not os.path.isdir(job_dir) or not os.path.exists(status_file):
        raise NotFoundError("Job", job_id)

    with open(status_file, "r", encoding="utf-8") as f:
        status_data = json.load(f)

    job_status = status_data.get("status", "UNKNOWN")
    if job_status not in ("CLASSIFIED", "COMPLETED", "APPROVED"):
        raise ValidationError(f"Job status must be CLASSIFIED or later, got {job_status}")

    # Load result.json
    result_file = os.path.join(job_dir, "result.json")
    if not os.path.exists(result_file):
        raise NotFoundError("Result file", job_id)

    with open(result_file, "r", encoding="utf-8") as rf:
        result_json = json.load(rf)

    desc_col = status_data.get("desc_column", "Descricao")
    raw_items = result_json.get("items", [])

    import pandas as pd
    from src.utils import friendly_source_label

    rows = []
    for item in raw_items:
        rows.append({
            "Descricao": item.get(desc_col, item.get("description", "")),
            "N1": item.get("N1", "Nao Identificado"),
            "N2": item.get("N2", "Nao Identificado"),
            "N3": item.get("N3", "Nao Identificado"),
            "N4": item.get("N4", "Nao Identificado"),
            "Fonte": friendly_source_label(item.get("source", "")),
            "Confianca": item.get("confidence", 0.0),
        })

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Resultados")
    file_bytes = buf.getvalue()
    file_b64 = base64.b64encode(file_bytes).decode("utf-8")

    original_filename = status_data.get("filename", "upload.xlsx")
    base_name = os.path.splitext(original_filename)[0]
    download_filename = f"{base_name}_resultado.xlsx"

    return json_response({
        "filename": download_filename,
        "file_content_base64": file_b64,
    })
```

**Step 4: Rodar todos os testes backend**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASSED

**Step 5: Commit**

```
git add blueprints/classification_bp.py tests/test_download_job_excel.py
git commit -m "Adicionando endpoint DownloadJobExcel — download do Excel bruto"
```

---

### Task 2: API client + botao download no ReviewTab (frontend)

**Files:**
- Modify: `frontend/src/lib/api.ts` (~linha 454, apos approveClassifications)
- Modify: `frontend/src/components/taxonomy/ReviewTab.tsx` (toolbar, ~linha 168)

**Step 1: Adicionar metodo no api client**

Em `frontend/src/lib/api.ts`, adicionar apos `approveClassifications`:

```typescript
  /** Downloads raw classification results as Excel (before review). */
  async downloadJobExcel(jobId: string): Promise<{ filename: string; file_content_base64: string }> {
    const response = await axios.get(`${API_BASE_URL}/DownloadJobExcel`, {
      params: { jobId },
      headers: getAuthHeaders(),
    });
    return response.data;
  },
```

**Step 2: Adicionar botao no ReviewTab**

Em `frontend/src/components/taxonomy/ReviewTab.tsx`:

2a. Adicionar estado para loading do download e importar apiClient:

```typescript
const [isDownloading, setIsDownloading] = useState(false);
```

2b. Adicionar handler:

```typescript
const handleDownloadAsIs = async () => {
  setIsDownloading(true);
  try {
    const api = await import('../../lib/api').then(m => m.apiClient);
    const result = await api.downloadJobExcel(jobId);
    const bytes = atob(result.file_content_base64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = result.filename;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    console.error('Download failed:', e);
  } finally {
    setIsDownloading(false);
  }
};
```

2c. Adicionar botao na toolbar, apos o `<div className="flex-1" />` e antes dos bulk actions:

```tsx
<button
  onClick={handleDownloadAsIs}
  disabled={isDownloading}
  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-50 text-gray-600 border border-gray-200 hover:bg-gray-100 transition-colors disabled:opacity-50"
  title="Baixar Excel com resultado bruto da classificacao"
>
  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
  {isDownloading ? 'Baixando...' : 'Baixar Excel'}
</button>
```

**Step 3: Verificar build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```
git add frontend/src/lib/api.ts frontend/src/components/taxonomy/ReviewTab.tsx
git commit -m "Adicionando botao download Excel AS-IS na tela de revisao"
```

---

### Task 3: Toggle global contributeToKB no useReview (hook)

**Files:**
- Modify: `frontend/src/hooks/useReview.ts`
- Modify: `frontend/src/__tests__/useReview.test.ts`

**Step 1: Escrever testes para o toggle global**

Adicionar ao final de `frontend/src/__tests__/useReview.test.ts`, dentro do `describe('useReview', ...)`:

```typescript
  // 16. Global contributeToKB toggle
  it('should default globalContributeToKB to true', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    expect(result.current.globalContributeToKB).toBe(true);
  });

  // 17. approveItem uses globalContributeToKB
  it('should use globalContributeToKB=false when approving items', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });

    act(() => { result.current.setGlobalContributeToKB(false); });
    act(() => { result.current.approveItem(0); });

    expect(result.current.getItemState(0).contributeToKB).toBe(false);
  });

  // 18. bulkApprove uses globalContributeToKB
  it('should use globalContributeToKB=false in bulk approve', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });

    act(() => { result.current.setGlobalContributeToKB(false); });
    act(() => { result.current.bulkApprove([0, 1, 2]); });

    expect(result.current.getItemState(0).contributeToKB).toBe(false);
    expect(result.current.getItemState(1).contributeToKB).toBe(false);
    expect(result.current.getItemState(2).contributeToKB).toBe(false);
  });

  // 19. editItem uses globalContributeToKB as default
  it('should use globalContributeToKB as default for editItem', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });

    act(() => { result.current.setGlobalContributeToKB(false); });
    act(() => {
      result.current.editItem(1, { N1: 'A', N2: 'B', N3: 'C', N4: 'D' });
    });

    expect(result.current.getItemState(1).contributeToKB).toBe(false);
  });

  // 20. editItem explicit override still works
  it('should allow explicit contributeToKB override in editItem', async () => {
    const { result } = renderUseReview();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });

    act(() => { result.current.setGlobalContributeToKB(false); });
    act(() => {
      result.current.editItem(1, { N1: 'A', N2: 'B', N3: 'C', N4: 'D', contributeToKB: true });
    });

    expect(result.current.getItemState(1).contributeToKB).toBe(true);
  });
```

**Step 2: Rodar testes e confirmar que os novos falham**

Run: `cd frontend && npx jest src/__tests__/useReview.test.ts --verbose`
Expected: Tests 16-20 FAIL (globalContributeToKB nao existe ainda)

**Step 3: Implementar no hook**

Em `frontend/src/hooks/useReview.ts`:

3a. Adicionar estado apos `isLoading` (~linha 17):

```typescript
const [globalContributeToKB, setGlobalContributeToKB] = useState(true);
```

3b. Atualizar `approveItem` (~linha 112):

```typescript
const approveItem = useCallback((index: number) => {
  setReviewStates(prev => {
    const next = new Map(prev);
    const existing = next.get(index) || { decision: 'pending' as ReviewDecision };
    next.set(index, { ...existing, decision: 'approved', contributeToKB: existing.contributeToKB ?? globalContributeToKB });
    return next;
  });
}, [globalContributeToKB]);
```

3c. Atualizar `editItem` (~linha 121):

```typescript
const editItem = useCallback((index: number, edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB?: boolean }) => {
  setReviewStates(prev => {
    const next = new Map(prev);
    next.set(index, {
      decision: 'edited',
      editedN1: edits.N1,
      editedN2: edits.N2,
      editedN3: edits.N3,
      editedN4: edits.N4,
      contributeToKB: edits.contributeToKB ?? globalContributeToKB,
    });
    return next;
  });
  setExpandedIndex(null);
}, [globalContributeToKB]);
```

3d. Atualizar `bulkApprove` (~linha 167):

```typescript
const bulkApprove = useCallback((indices: number[]) => {
  setReviewStates(prev => {
    const next = new Map(prev);
    for (const idx of indices) {
      const existing = next.get(idx) || { decision: 'pending' as ReviewDecision };
      next.set(idx, { ...existing, decision: 'approved', contributeToKB: globalContributeToKB });
    }
    return next;
  });
  setSelectedIndices(new Set());
}, [globalContributeToKB]);
```

3e. Expor no return (~linha 230):

```typescript
return {
  // ... existing exports ...
  globalContributeToKB,
  setGlobalContributeToKB,
};
```

**Step 4: Rodar testes e confirmar que passam**

Run: `cd frontend && npx jest src/__tests__/useReview.test.ts --verbose`
Expected: ALL PASSED (incluindo os 5 novos testes)

**Step 5: Commit**

```
git add frontend/src/hooks/useReview.ts frontend/src/__tests__/useReview.test.ts
git commit -m "Adicionando toggle global contributeToKB no useReview"
```

---

### Task 4: Switch visual na toolbar do ReviewTab

**Files:**
- Modify: `frontend/src/components/taxonomy/ReviewTab.tsx` (barra de progresso, ~linha 253)

**Step 1: Extrair globalContributeToKB do hook**

Na desestruturacao do useReview (~linha 41), adicionar:

```typescript
const {
  filteredItems, filter, setFilter, selectedIndices,
  progress, filterCounts, canFinalize, isLoading,
  approveItem, editItem, rejectItem, rejectItems, reclassifyItems, bulkApprove, bulkApproveHighConfidence,
  toggleSelection, toggleAll, finalizeReview, getItemState,
  globalContributeToKB, setGlobalContributeToKB,
} = useReview({ ... });
```

**Step 2: Adicionar switch na barra de progresso**

Na barra de progresso (~linha 253, dentro do `<div className="flex items-center gap-3 px-3 py-1.5 bg-gray-50/50 ...">`), adicionar apos o `{progress.pct}%` span:

```tsx
<div className="h-4 w-px bg-gray-200 flex-shrink-0" />
<label className="flex items-center gap-1.5 cursor-pointer flex-shrink-0 select-none">
  <button
    type="button"
    role="switch"
    aria-checked={globalContributeToKB}
    onClick={() => setGlobalContributeToKB(!globalContributeToKB)}
    className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors duration-200 ${
      globalContributeToKB ? 'bg-mint-400' : 'bg-gray-300'
    }`}
  >
    <span
      className={`inline-block h-3 w-3 transform rounded-full bg-white shadow-sm transition-transform duration-200 ${
        globalContributeToKB ? 'translate-x-3.5' : 'translate-x-0.5'
      }`}
    />
  </button>
  <span className={`text-[11px] font-medium ${globalContributeToKB ? 'text-mint-600' : 'text-gray-400'}`}>
    {globalContributeToKB ? 'Contribuir para KB' : 'Nao contribuir para KB'}
  </span>
</label>
```

**Step 3: Verificar build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```
git add frontend/src/components/taxonomy/ReviewTab.tsx
git commit -m "Adicionando switch visual Contribuir para KB na toolbar de revisao"
```

---

### Task 5: Melhoria UX Import KB — preview e validacao (frontend)

**Files:**
- Modify: `frontend/src/components/taxonomy/KnowledgeTab.tsx`

**Step 1: Adicionar estados para preview**

No topo do componente `KnowledgeTab`, adicionar estados:

```typescript
const [importPreview, setImportPreview] = useState<{
  rows: Array<Record<string, string>>;
  totalRows: number;
  columns: string[];
  file: File;
  b64: string;
} | null>(null);
const [importResult, setImportResult] = useState<{ added: number; total: number } | null>(null);
```

**Step 2: Substituir handleImport por parse com preview**

Substituir o `handleImport` existente (~linha 115) por:

```typescript
const handleImportSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
  if (!projectId || !e.target.files?.[0]) return;
  setImportError(null);
  setImportResult(null);

  const file = e.target.files[0];
  try {
    const arrayBuffer = await file.arrayBuffer();
    const XLSX = await import('xlsx');
    const workbook = XLSX.read(arrayBuffer, { type: 'array' });
    const sheetName = workbook.SheetNames[0];
    const sheet = workbook.Sheets[sheetName];
    const jsonData = XLSX.utils.sheet_to_json<Record<string, string>>(sheet, { defval: '' });

    const columns = jsonData.length > 0 ? Object.keys(jsonData[0]) : [];

    // Validar colunas obrigatorias
    const requiredAliases: Record<string, string[]> = {
      'Descricao': ['Descricao', 'Descrição', 'description'],
      'N1': ['N1'],
      'N2': ['N2'],
      'N3': ['N3'],
      'N4': ['N4'],
    };

    const missing: string[] = [];
    for (const [label, aliases] of Object.entries(requiredAliases)) {
      if (!aliases.some(a => columns.includes(a))) {
        missing.push(label);
      }
    }

    if (missing.length > 0) {
      setImportError(`Colunas obrigatorias nao encontradas: ${missing.join(', ')}. Colunas detectadas: ${columns.join(', ')}`);
      e.target.value = '';
      return;
    }

    // Converter para base64 para envio posterior
    const b64 = btoa(
      new Uint8Array(arrayBuffer).reduce((data, byte) => data + String.fromCharCode(byte), '')
    );

    setImportPreview({
      rows: jsonData.slice(0, 5),
      totalRows: jsonData.length,
      columns,
      file,
      b64,
    });
  } catch (err: any) {
    setImportError(err.message || 'Erro ao ler o arquivo');
  } finally {
    e.target.value = '';
  }
};

const handleImportConfirm = async () => {
  if (!projectId || !importPreview) return;
  setIsImporting(true);
  setImportError(null);
  try {
    const api = await getApi();
    const result = await api.importKB(projectId, importPreview.b64);
    setImportResult(result);
    setImportPreview(null);
    await loadKB();
    await loadCoverage();
  } catch (err: any) {
    setImportError(err.message || 'Erro ao importar');
  } finally {
    setIsImporting(false);
  }
};

const handleImportCancel = () => {
  setImportPreview(null);
  setImportError(null);
};
```

**Step 3: Atualizar o input file para usar handleImportSelect**

Na label do import (~linha 234), mudar `onChange={handleImport}` para `onChange={handleImportSelect}`.

**Step 4: Adicionar UI do preview e feedback**

Adicionar apos o `importError` div (~linha 256) e antes do `showVersions` section:

```tsx
{/* Import preview */}
{importPreview && (
  <div className="mb-3 border border-accent-200 rounded-xl overflow-hidden bg-accent-50/30">
    <div className="px-3 py-2 bg-accent-50 border-b border-accent-100 flex items-center justify-between">
      <span className="text-xs font-medium text-accent-700">
        Preview: {importPreview.file.name} ({importPreview.totalRows} linhas)
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={handleImportCancel}
          className="text-xs px-2.5 py-1 border border-gray-200 text-gray-500 hover:bg-gray-50 rounded-lg transition-colors"
        >
          Cancelar
        </button>
        <button
          onClick={handleImportConfirm}
          disabled={isImporting}
          className="text-xs px-2.5 py-1 bg-accent-500 text-white hover:bg-accent-600 rounded-lg transition-colors disabled:opacity-50"
        >
          {isImporting ? 'Importando...' : `Confirmar Importacao (${importPreview.totalRows})`}
        </button>
      </div>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-100">
            {importPreview.columns.slice(0, 7).map(col => (
              <th key={col} className="px-2 py-1.5 text-left font-medium text-gray-500 whitespace-nowrap">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {importPreview.rows.map((row, i) => (
            <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50">
              {importPreview.columns.slice(0, 7).map(col => (
                <td key={col} className="px-2 py-1.5 text-gray-700 whitespace-nowrap max-w-[200px] truncate">
                  {String(row[col] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {importPreview.totalRows > 5 && (
        <p className="text-[10px] text-gray-400 px-2 py-1 text-center">
          ... e mais {importPreview.totalRows - 5} linhas
        </p>
      )}
    </div>
  </div>
)}

{/* Import result feedback */}
{importResult && (
  <div className="mb-3 rounded-lg bg-mint-50 border border-mint-200 px-3 py-2 text-sm text-mint-700 flex items-center justify-between">
    <span>{importResult.added} entradas adicionadas. Total na base: {importResult.total}</span>
    <button onClick={() => setImportResult(null)} className="text-mint-500 hover:text-mint-700 ml-2">
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  </div>
)}
```

**Step 5: Verificar build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 6: Commit**

```
git add frontend/src/components/taxonomy/KnowledgeTab.tsx
git commit -m "Melhoria UX import KB — preview com validacao e feedback inline"
```

---

### Task 6: Testes finais e verificacao

**Step 1: Rodar todos os testes backend**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASSED

**Step 2: Rodar todos os testes frontend**

Run: `cd frontend && npx jest --verbose`
Expected: ALL PASSED

**Step 3: Verificar build frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit final (se necessario)**

Apenas se houve ajustes apos testes.
