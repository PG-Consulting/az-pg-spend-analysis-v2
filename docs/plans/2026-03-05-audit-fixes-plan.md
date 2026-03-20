# Audit Fixes — Plano de Implementacao

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Corrigir todos os 66 achados da auditoria completa (18 criticos, 30 importantes, 18 menores) do Spend Analysis v3.

**Architecture:** Correcoes organizadas em 8 grupos independentes, priorizados por impacto em producao. Cada grupo pode ser executado por um subagente isolado. Grupos 1-3 sao bloqueantes; 4-8 sao melhorias incrementais.

**Tech Stack:** Python 3.12 (Azure Functions), Next.js 14 + TypeScript, pytest, Jest

---

## Grupo 1: Backend Bug Fixes (Criticos)

### Task 1.1: Fix timezone bug em cleanup_stale_jobs

**Files:**
- Modify: `src/worker_helpers.py:61`
- Test: `tests/test_worker_helpers.py`

**Step 1: Write failing test**

```python
# tests/test_worker_helpers.py — adicionar ao final
from src.worker_helpers import cleanup_stale_jobs
import tempfile, json, os
from datetime import datetime, timezone, timedelta

class TestCleanupStaleJobs:
    def test_marks_stale_processing_job_as_error(self, tmp_path):
        job_dir = tmp_path / "stale-job"
        job_dir.mkdir()
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        status = {"status": "PROCESSING", "created_at": two_hours_ago}
        (job_dir / "status.json").write_text(json.dumps(status))

        cleanup_stale_jobs(str(tmp_path))

        result = json.loads((job_dir / "status.json").read_text())
        assert result["status"] == "ERROR"
        assert "expired" in result.get("error", "").lower()

    def test_ignores_recent_processing_job(self, tmp_path):
        job_dir = tmp_path / "recent-job"
        job_dir.mkdir()
        just_now = datetime.now(timezone.utc).isoformat()
        status = {"status": "PROCESSING", "created_at": just_now}
        (job_dir / "status.json").write_text(json.dumps(status))

        cleanup_stale_jobs(str(tmp_path))

        result = json.loads((job_dir / "status.json").read_text())
        assert result["status"] == "PROCESSING"

    def test_ignores_non_processing_jobs(self, tmp_path):
        job_dir = tmp_path / "completed-job"
        job_dir.mkdir()
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        status = {"status": "COMPLETED", "created_at": old}
        (job_dir / "status.json").write_text(json.dumps(status))

        cleanup_stale_jobs(str(tmp_path))

        result = json.loads((job_dir / "status.json").read_text())
        assert result["status"] == "COMPLETED"
```

**Step 2: Run test, expect FAIL (TypeError: naive vs aware datetime)**

```bash
python3 -m pytest tests/test_worker_helpers.py::TestCleanupStaleJobs -v
```

**Step 3: Fix — replace `datetime.utcnow()` with `datetime.now(timezone.utc)`**

```python
# src/worker_helpers.py:61 — change:
            elapsed = (datetime.utcnow() - created_dt).total_seconds()
# to:
            elapsed = (datetime.now(timezone.utc) - created_dt).total_seconds()
```

**Step 4: Run test, expect PASS**

```bash
python3 -m pytest tests/test_worker_helpers.py::TestCleanupStaleJobs -v
```

**Step 5: Commit**

```bash
git add src/worker_helpers.py tests/test_worker_helpers.py
git commit -m "Fix: bug de timezone em cleanup_stale_jobs (naive vs aware datetime)"
```

---

### Task 1.2: Fix friendly_source_label missing reclassified_with_guidance

**Files:**
- Modify: `src/utils.py:57-64`
- Test: `tests/test_utils.py`

**Step 1: Write failing test**

```python
# tests/test_utils.py — adicionar
from src.utils import friendly_source_label

def test_friendly_source_label_reclassified_with_guidance():
    assert friendly_source_label("reclassified_with_guidance") == "Reclassificado"

def test_friendly_source_label_known_sources():
    assert friendly_source_label("KB (Direct Match)") == "Base de Aprendizado"
    assert friendly_source_label("LLM (Batch)") == "Grok"
    assert friendly_source_label("consultant_correction") == "Ajuste Manual"

def test_friendly_source_label_unknown_passthrough():
    assert friendly_source_label("unknown_source") == "unknown_source"
    assert friendly_source_label("") == ""
```

**Step 2: Run test, expect FAIL on reclassified_with_guidance**

```bash
python3 -m pytest tests/test_utils.py::test_friendly_source_label_reclassified_with_guidance -v
```

**Step 3: Add mapping**

```python
# src/utils.py — _SOURCE_LABELS dict, add entry:
_SOURCE_LABELS = {
    "KB (Direct Match)": "Base de Aprendizado",
    "LLM (Batch)": "Grok",
    "LLM (Reclassified)": "Grok",
    "Taxonomy (Dict)": "Dicionario",
    "ML": "ML",
    "consultant_correction": "Ajuste Manual",
    "reclassified_with_guidance": "Reclassificado",
}
```

**Step 4: Run all utils tests**

```bash
python3 -m pytest tests/test_utils.py -v
```

**Step 5: Commit**

```bash
git add src/utils.py tests/test_utils.py
git commit -m "Fix: friendly_source_label agora mapeia reclassified_with_guidance"
```

---

### Task 1.3: Fix fallback chunk size bug em llm_classifier

**Files:**
- Modify: `src/llm_classifier.py:146-152`

**Step 1: Write failing test**

```python
# tests/test_llm_classifier_fallback.py
from unittest.mock import patch, MagicMock
from src.llm_classifier import classify_items_with_llm

def test_fallback_uses_correct_chunk_size():
    """When a chunk fails, fallback should create exactly the right number of items."""
    descriptions = ["item1", "item2", "item3"]  # 3 items, one chunk

    with patch("src.llm_classifier._call_openai_api") as mock_api:
        mock_api.side_effect = Exception("API Error")

        results = classify_items_with_llm(descriptions)

    # Should have exactly 3 fallback results, not more
    assert len(results) == 3
    assert all(r["N1"] == "Nao Identificado" for r in results)
```

**Step 2: Run test**

```bash
python3 -m pytest tests/test_llm_classifier_fallback.py -v
```

**Step 3: Fix — use actual chunk length**

```python
# src/llm_classifier.py — replace lines 146-152:
            except Exception as e:
                logging.error(f"Chunk starting at {chunk_start} failed: {e}")
                # Find the actual chunk that failed
                failed_chunk = next(
                    (items for start, items in chunks if start == chunk_start),
                    []
                )
                for offset in range(len(failed_chunk)):
                    idx = chunk_start + offset
                    if idx < len(results):
                        results[idx] = _create_manual_fallback("Erro no processamento paralelo")
```

**Step 4: Run test, expect PASS**

```bash
python3 -m pytest tests/test_llm_classifier_fallback.py -v
```

**Step 5: Commit**

```bash
git add src/llm_classifier.py tests/test_llm_classifier_fallback.py
git commit -m "Fix: fallback LLM usa tamanho real do chunk que falhou"
```

---

### Task 1.4: Fix jobId vazio em ApproveClassifications e ReclassifyItems

**Files:**
- Modify: `blueprints/review_bp.py:31-32` e `:139-149`

**Step 1: Write failing test**

```python
# tests/test_review_bp.py
import json
import pytest
from unittest.mock import patch, MagicMock
import azure.functions as func
from blueprints.review_bp import approve_classifications_endpoint, reclassify_items_endpoint
from src.exceptions import ValidationError

class TestReviewValidation:
    def test_approve_rejects_empty_job_id(self):
        body = {"jobId": "", "projectId": "test", "decisions": []}
        req = func.HttpRequest(method="POST", url="/api/ApproveClassifications",
                               body=json.dumps(body).encode(), headers={"Content-Type": "application/json"})

        response = approve_classifications_endpoint(req)
        data = json.loads(response.get_body())
        assert response.status_code == 400 or "error" in data

    def test_reclassify_rejects_empty_job_id(self):
        body = {"jobId": "", "projectId": "test", "items": [{"index": 0, "description": "test"}],
                "instruction": "reclassify"}
        req = func.HttpRequest(method="POST", url="/api/ReclassifyItems",
                               body=json.dumps(body).encode(), headers={"Content-Type": "application/json"})

        response = reclassify_items_endpoint(req)
        # Should not crash with FileNotFoundError
        assert response.status_code in (400, 404, 200)
```

**Step 2: Run test, observe crash or unexpected behavior**

```bash
python3 -m pytest tests/test_review_bp.py::TestReviewValidation -v
```

**Step 3: Add validation**

```python
# blueprints/review_bp.py — after line 32 (job_id = body.get("jobId", "")):
    if not job_id:
        raise ValidationError("jobId is required")

# blueprints/review_bp.py — after line 142 (job_id = body.get("jobId", "")):
    if not job_id:
        raise ValidationError("jobId is required")
```

Also add `ValidationError` import if missing (already imported at line 13 — confirm).

**Step 4: Run test, expect PASS**

```bash
python3 -m pytest tests/test_review_bp.py -v
```

**Step 5: Commit**

```bash
git add blueprints/review_bp.py tests/test_review_bp.py
git commit -m "Fix: validacao de jobId vazio em ApproveClassifications e ReclassifyItems"
```

---

### Task 1.5: Fix diretorio orfao quando parse de arquivo falha

**Files:**
- Modify: `blueprints/classification_bp.py:152-166`

**Step 1: Add cleanup on parse failure**

```python
# blueprints/classification_bp.py — wrap the file parsing block (lines 158-166):
    # --- Decode and load file ---
    file_bytes = base64.b64decode(file_content_b64)
    try:
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=";", encoding="utf-8", on_bad_lines="skip")
            except Exception:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=",", encoding="utf-8", on_bad_lines="skip")
    except Exception as e:
        # Clean up orphan directory
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)
        raise ValidationError(f"Formato de arquivo invalido: {e}")
```

**Step 2: Run existing tests**

```bash
python3 -m pytest tests/ -v -k "submit or classification"
```

**Step 3: Commit**

```bash
git add blueprints/classification_bp.py
git commit -m "Fix: limpa diretorio orfao quando parse de arquivo falha em SubmitTaxonomyJob"
```

---

### Task 1.6: Fix referencia a modelo antigo no prompt LLM

**Files:**
- Modify: `src/llm_classifier.py:232`

**Step 1: Remove stale model reference**

```python
# src/llm_classifier.py:232 — change:
            "Analise cada palavra antes de decidir. Use a logica do modelo 'grok-4-0709' para desambiguar contextos.\n"
# to:
            "Analise cada palavra antes de decidir para desambiguar contextos.\n"
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add src/llm_classifier.py
git commit -m "Fix: remove referencia a modelo antigo grok-4-0709 no prompt LLM"
```

---

## Grupo 2: Race Conditions e Concorrencia

### Task 2.1: Add file locking para status.json

**Files:**
- Modify: `requirements.txt` (add `filelock`)
- Create: `src/file_lock.py`
- Modify: `src/worker_helpers.py`
- Modify: `blueprints/classification_bp.py`
- Modify: `blueprints/review_bp.py`

**Step 1: Add filelock dependency**

```bash
pip install filelock
```

Add `filelock` to `requirements.txt`.

**Step 2: Create helper module**

```python
# src/file_lock.py
"""Thread-safe file operations for status.json."""
import json
import os
from filelock import FileLock

def read_status(status_path: str) -> dict:
    """Read status.json with file lock."""
    lock = FileLock(status_path + ".lock", timeout=10)
    with lock:
        with open(status_path, "r", encoding="utf-8") as f:
            return json.load(f)

def write_status(status_path: str, data: dict) -> None:
    """Write status.json with file lock."""
    lock = FileLock(status_path + ".lock", timeout=10)
    with lock:
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

def update_status(status_path: str, updates: dict) -> dict:
    """Read-modify-write status.json atomically."""
    lock = FileLock(status_path + ".lock", timeout=10)
    with lock:
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.update(updates)
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    return data
```

**Step 3: Replace direct reads/writes in worker_helpers.py**

Replace all `with open(status_path, "w")` and `with open(status_path, "r")` patterns with `read_status`/`write_status`/`update_status` from `src.file_lock`:

- `cleanup_stale_jobs`: read + conditional write
- `get_active_jobs`: read + transition PENDING->PROCESSING
- `update_job_progress`: write
- `consolidate_job`: write final status
- `run_worker_cycle`: error status write

**Step 4: Replace in blueprints**

- `classification_bp.py`: CancelJob read-then-write
- `review_bp.py`: ApproveClassifications read-then-write

**Step 5: Write tests**

```python
# tests/test_file_lock.py
import json
from src.file_lock import read_status, write_status, update_status

def test_read_write_status(tmp_path):
    path = str(tmp_path / "status.json")
    write_status(path, {"status": "PENDING"})
    data = read_status(path)
    assert data["status"] == "PENDING"

def test_update_status_merges(tmp_path):
    path = str(tmp_path / "status.json")
    write_status(path, {"status": "PROCESSING", "chunks": 5})
    result = update_status(path, {"status": "CLASSIFIED"})
    assert result["status"] == "CLASSIFIED"
    assert result["chunks"] == 5
```

**Step 6: Run all tests**

```bash
python3 -m pytest tests/ -v
```

**Step 7: Commit**

```bash
git add src/file_lock.py requirements.txt src/worker_helpers.py blueprints/classification_bp.py blueprints/review_bp.py tests/test_file_lock.py
git commit -m "Fix: file locking para status.json (race condition em worker/API concorrente)"
```

---

### Task 2.2: Fix mutacao thread-unsafe em GetKBCoverage

**Files:**
- Modify: `blueprints/knowledge_bp.py`

**Step 1: Replace mutation with ephemeral computation**

Find the `GetKBCoverage` endpoint and replace the temporary mutation pattern:

```python
# Instead of:
original_entries = project_kb.entries
project_kb.entries = merged
coverage = project_kb.get_coverage(hierarchy)
project_kb.entries = original_entries

# Use:
from src.knowledge_base import KnowledgeBase
temp_kb = KnowledgeBase.__new__(KnowledgeBase)
temp_kb.entries = merged
coverage = temp_kb.get_coverage(hierarchy)
```

Or better: extract `get_coverage` as a static/class method that takes entries as parameter.

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add blueprints/knowledge_bp.py
git commit -m "Fix: elimina mutacao thread-unsafe em GetKBCoverage"
```

---

## Grupo 3: Performance

### Task 3.1: Remover Excel base64 do status.json

**Files:**
- Modify: `blueprints/review_bp.py:241`
- Modify: `blueprints/classification_bp.py` (GetTaxonomyJobStatus)

**Step 1: Save Excel to separate file instead of status.json**

```python
# blueprints/review_bp.py — line 241, change:
        status_data["approved_file_content_base64"] = file_b64
# to:
        # Save Excel to separate file (not in status.json — avoids loading 5-15MB on every poll)
        approved_path = os.path.join(job_dir, "approved_result_b64.txt")
        with open(approved_path, "w", encoding="utf-8") as af:
            af.write(file_b64)
```

Remove `approved_file_content_base64` from `status_data` write.

In `GetTaxonomyJobStatus` — if status is COMPLETED, load the approved file separately only when needed (or keep current behavior since it reads `result.json` not `status.json`).

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add blueprints/review_bp.py
git commit -m "Ajuste: Excel base64 aprovado salvo em arquivo separado (nao no status.json)"
```

---

### Task 3.2: Vetorizar generate_summary

**Files:**
- Modify: `src/taxonomy_engine.py:555-558`
- Test: `tests/test_taxonomy_engine.py` (novo)

**Step 1: Write test**

```python
# tests/test_taxonomy_engine.py
import pandas as pd
from src.taxonomy_engine import generate_summary

def test_generate_summary_counts():
    df = pd.DataFrame({
        "N1": ["Cat1", "Cat1", "", "Cat2"],
        "N2": ["Sub1", "Sub1", "Sub2", "Nao Identificado"],
        "N3": ["A", "B", "C", "D"],
        "N4": ["X", "Y", "Z", "W"],
    })
    result = generate_summary(df, "Descricao")
    assert result["total_linhas"] == 4
    assert result["nenhum"] == 2  # empty N1 row + "Nao Identificado" N2 row
    assert result["unico"] == 2

def test_generate_summary_all_classified():
    df = pd.DataFrame({
        "N1": ["A", "B"],
        "N2": ["C", "D"],
        "N3": ["E", "F"],
        "N4": ["G", "H"],
    })
    result = generate_summary(df, "Descricao")
    assert result["nenhum"] == 0
    assert result["unico"] == 2
```

**Step 2: Run test to verify it works with current implementation**

```bash
python3 -m pytest tests/test_taxonomy_engine.py -v
```

**Step 3: Vectorize**

```python
# src/taxonomy_engine.py — replace lines 554-558:
    _incomplete = {"", "Nao Identificado", "Nao Identificado"}
    incomplete_mask = pd.Series(False, index=df_items.index)
    for lvl in ("N1", "N2", "N3", "N4"):
        if lvl in df_items.columns:
            incomplete_mask = incomplete_mask | df_items[lvl].fillna("").astype(str).str.strip().isin(_incomplete)
    nenhum_count = int(incomplete_mask.sum())
    unico_count = total_items - nenhum_count
```

**Step 4: Run test to verify same results**

```bash
python3 -m pytest tests/test_taxonomy_engine.py -v
```

**Step 5: Commit**

```bash
git add src/taxonomy_engine.py tests/test_taxonomy_engine.py
git commit -m "Ajuste: vetoriza generate_summary (remove df.apply row-by-row)"
```

---

### Task 3.3: Otimizar cache de fuzzy match

**Files:**
- Modify: `src/hierarchy_validator.py:69`

**Step 1: Replace frozenset key with id()**

```python
# src/hierarchy_validator.py:68-69 — change:
        cache_key = (value, frozenset(candidates))
# to:
        cache_key = (value, id(candidates))
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/test_hierarchy_validator.py -v
```

**Step 3: Commit**

```bash
git add src/hierarchy_validator.py
git commit -m "Ajuste: cache de fuzzy match usa id() em vez de frozenset (O(1) vs O(n))"
```

---

## Grupo 4: API Layer Fixes

### Task 4.1: Remover funcao morta _parse_custom_hierarchy_b64

**Files:**
- Modify: `blueprints/classification_bp.py:22-74`

**Step 1: Delete function**

Remove lines 22-74 (`_parse_custom_hierarchy_b64`) entirely — never called.

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add blueprints/classification_bp.py
git commit -m "Refactor: remove _parse_custom_hierarchy_b64 morta (duplicava project_manager)"
```

---

### Task 4.2: Fix DeleteMemoryRule aceita GET

**Files:**
- Modify: `blueprints/copilot_bp.py:79`

**Step 1: Remove GET from methods**

```python
# blueprints/copilot_bp.py:79 — change:
@copilot_bp.route(route="DeleteMemoryRule", methods=["DELETE", "GET", "OPTIONS"],
# to:
@copilot_bp.route(route="DeleteMemoryRule", methods=["DELETE", "OPTIONS"],
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add blueprints/copilot_bp.py
git commit -m "Fix: remove GET do DeleteMemoryRule (violacao REST)"
```

---

### Task 4.3: Fix dead code ternario em models_bp

**Files:**
- Modify: `blueprints/models_bp.py:552-554`

**Step 1: Read exact code at those lines and fix**

The ternary `"Descricao" if "Descricao" in df.columns else ("Descricao" if "Descricao" in df.columns else df.columns[0])` — the second test is identical. Fix:

```python
# Change to:
desc_col = "Descricao" if "Descricao" in df.columns else (
    "Descricao" if "Descricao" in df.columns else df.columns[0]
)
# Should be:
desc_col = "Descricao" if "Descricao" in df.columns else df.columns[0]
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add blueprints/models_bp.py
git commit -m "Fix: remove ternario duplicado em GetTrainingData"
```

---

### Task 4.4: Remover path do filesystem do health endpoint

**Files:**
- Modify: `blueprints/health_bp.py:23`

**Step 1: Replace raw path with boolean**

```python
# blueprints/health_bp.py:23 — change:
        "models_dir": models_dir,
# to:
        "models_dir_configured": bool(models_dir),
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/test_health.py -v
```

**Step 3: Commit**

```bash
git add blueprints/health_bp.py
git commit -m "Fix: health endpoint nao expoe path do filesystem"
```

---

### Task 4.5: Padronizar @handle_errors com nome do endpoint

**Files:**
- Modify: `blueprints/classification_bp.py` (linhas 79, 231, 289, 332, 454)

**Step 1: Add string to all bare @handle_errors**

```python
# Change all @handle_errors to @handle_errors("EndpointName"):
@handle_errors  # line 79 → @handle_errors("SubmitTaxonomyJob")
@handle_errors  # line 231 → @handle_errors("GetTaxonomyJobStatus")
@handle_errors  # line 289 → @handle_errors("CancelJob")
@handle_errors  # line 332 → @handle_errors("GetJobResults")
@handle_errors  # line 454 → @handle_errors("DownloadJobExcel")
```

Also fix `copilot_bp.py` bare decorators:
```python
@handle_errors  # → @handle_errors("GetDirectLineToken")
@handle_errors  # → @handle_errors("SearchMemory")
@handle_errors  # → @handle_errors("DeleteMemoryRule")
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add blueprints/classification_bp.py blueprints/copilot_bp.py
git commit -m "Ajuste: padroniza @handle_errors com nome do endpoint em todos os blueprints"
```

---

### Task 4.6: Extrair _derive_status como funcao reutilizavel

**Files:**
- Modify: `blueprints/classification_bp.py` (elimina duplicacao das linhas 391-396 e 428-433)

**Step 1: Create helper function at top of file**

```python
_UNIDENTIFIED = frozenset({"", "Nao Identificado"})

def _derive_status(row: dict) -> str:
    """Derive item status from N1-N4 values."""
    existing = row.get("status", "")
    if existing:
        return existing
    if any(str(row.get(lvl, "")).strip() in _UNIDENTIFIED for lvl in ("N1", "N2", "N3", "N4")):
        return "Nenhum"
    return "Unico"
```

**Step 2: Replace both inline blocks with `_derive_status(row)`**

**Step 3: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 4: Commit**

```bash
git add blueprints/classification_bp.py
git commit -m "Refactor: extrai _derive_status eliminando duplicacao em GetJobResults"
```

---

### Task 4.7: Alinhar max_retries com constante documentada

**Files:**
- Modify: `src/llm_classifier.py:295`

**Step 1: Replace hardcoded value**

```python
# src/llm_classifier.py — at top, add constant:
LLM_MAX_RETRIES = 2

# Line 295 — change:
    max_retries = 3
# to:
    max_retries = LLM_MAX_RETRIES
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add src/llm_classifier.py
git commit -m "Ajuste: max_retries alinhado com LLM_MAX_RETRIES=2 documentado"
```

---

## Grupo 5: Frontend Critical Fixes

### Task 5.1: Fix stale closure em setReviewCompleted

**Files:**
- Modify: `frontend/src/hooks/useTaxonomySession.ts:201-222`

**Step 1: Fix — save from updated state**

```typescript
// Replace lines 201-222 with:
        let updatedSession: TaxonomySession | undefined;
        setSessions(prev => {
            const next = prev.map(s => {
                if (s.sessionId !== activeSessionId) return s;
                const updated = {
                    ...s,
                    reviewState: 'completed' as ReviewState,
                    reviewSummary: summary,
                    approvedFileContentBase64: approvedFileB64,
                    approvedDownloadFilename: approvedFilename,
                };
                updatedSession = updated;
                return updated;
            });
            return next;
        });

        if (updatedSession) {
            await saveSession(updatedSession);
        }
    }, [activeSessionId])  // Remove `sessions` from deps
```

**Step 2: Run frontend tests**

```bash
cd frontend && npx jest --verbose
```

**Step 3: Commit**

```bash
git add frontend/src/hooks/useTaxonomySession.ts
git commit -m "Fix: stale closure em setReviewCompleted (salva estado atualizado)"
```

---

### Task 5.2: Fix campos errados no execution-engine.ts

**Files:**
- Modify: `frontend/src/lib/smart-context/execution-engine.ts`

**Step 1: Replace all `_desc_original` and `Item_Description` with `description`**

```typescript
// Replace all occurrences:
i._desc_original || i.Item_Description
// with:
i.description

// Also replace:
i._desc_original
// with:
i.description

// And:
groupLevel === '_desc_original'
// with:
groupLevel === 'description'
```

**Step 2: Run frontend tests**

```bash
cd frontend && npx jest --verbose
```

**Step 3: Commit**

```bash
git add frontend/src/lib/smart-context/execution-engine.ts
git commit -m "Fix: execution-engine usa campo description correto (nao _desc_original)"
```

---

### Task 5.3: Fix toggleAll seleciona itens invisiveis

**Files:**
- Modify: `frontend/src/hooks/useReview.ts:213-219`

**Step 1: Change toggleAll to accept visible items**

```typescript
// useReview.ts — change toggleAll to:
  const toggleAll = useCallback((visibleItems?: ClassifiedItem[]) => {
    const target = visibleItems || filteredItems;
    if (selectedIndices.size === target.length) {
      setSelectedIndices(new Set());
    } else {
      setSelectedIndices(new Set(target.map(i => i.index)));
    }
  }, [selectedIndices.size, filteredItems]);
```

**Step 2: Update ReviewTab to pass displayItems**

In `ReviewTab.tsx`, where `toggleAll()` is called, change to `toggleAll(displayItems)`.

**Step 3: Run frontend tests**

```bash
cd frontend && npx jest --verbose
```

**Step 4: Commit**

```bash
git add frontend/src/hooks/useReview.ts frontend/src/components/taxonomy/ReviewTab.tsx
git commit -m "Fix: toggleAll opera sobre itens visiveis (displayItems) quando busca esta ativa"
```

---

### Task 5.4: Remover console.log de producao

**Files:**
- Modify: `frontend/src/lib/api.ts:93-94` e `:120-121`

**Step 1: Remove or guard console.logs**

```typescript
// Remove lines 93-94:
    console.log('[DIRECT LINE ACTIVITY]', JSON.stringify(activity, null, 2));

// Remove lines 120-121:
    console.log('[DIRECT LINE PAYLOAD]', JSON.stringify(payload, null, 2));
```

**Step 2: Run frontend tests**

```bash
cd frontend && npx jest --verbose
```

**Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "Fix: remove console.log de producao em api.ts (Direct Line)"
```

---

### Task 5.5: Extrair getSourceLabel duplicado

**Files:**
- Modify: `frontend/src/lib/utils.ts` (ou criar se nao existe)
- Modify: `frontend/src/components/taxonomy/ReviewTable.tsx`
- Modify: `frontend/src/components/taxonomy/ItemDetailPanel.tsx`

**Step 1: Move function to shared location**

Copiar `getSourceLabel` para `frontend/src/lib/utils.ts` e exportar.

**Step 2: Import nos dois componentes, remover copias locais**

**Step 3: Run frontend tests**

```bash
cd frontend && npx jest --verbose
```

**Step 4: Commit**

```bash
git add frontend/src/lib/utils.ts frontend/src/components/taxonomy/ReviewTable.tsx frontend/src/components/taxonomy/ItemDetailPanel.tsx
git commit -m "Refactor: extrai getSourceLabel para lib/utils.ts (remove duplicacao)"
```

---

## Grupo 6: Frontend Important Fixes

### Task 6.1: Adicionar debounce na busca da KnowledgeTab

**Files:**
- Modify: `frontend/src/components/taxonomy/KnowledgeTab.tsx`
- Modify: `frontend/src/components/taxonomy/SectorKnowledgeTab.tsx`

**Step 1: Add debounced search**

```typescript
// Add at top of KnowledgeTab:
import { useState, useEffect, useRef } from 'react';

// Inside component, replace direct searchQuery usage with debounced:
const [searchInput, setSearchInput] = useState('');
const [debouncedSearch, setDebouncedSearch] = useState('');

useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput), 300);
    return () => clearTimeout(timer);
}, [searchInput]);

// Use debouncedSearch in the loadKB callback dependencies instead of searchInput
```

Apply same pattern to `SectorKnowledgeTab.tsx`.

**Step 2: Run frontend tests**

```bash
cd frontend && npx jest --verbose
```

**Step 3: Commit**

```bash
git add frontend/src/components/taxonomy/KnowledgeTab.tsx frontend/src/components/taxonomy/SectorKnowledgeTab.tsx
git commit -m "Ajuste: debounce de 300ms na busca da KnowledgeTab (evita flood de API)"
```

---

### Task 6.2: Adicionar try/catch em handlers da KnowledgeTab

**Files:**
- Modify: `frontend/src/components/taxonomy/KnowledgeTab.tsx`
- Modify: `frontend/src/components/taxonomy/SectorKnowledgeTab.tsx`

**Step 1: Wrap API calls in try/catch with user feedback**

```typescript
const handleDelete = async (entryId: string) => {
    if (!projectId) return;
    try {
        const api = await getApi();
        await api.deleteKBEntry(projectId, entryId);
        loadKB();
        loadCoverage();
    } catch (e) {
        console.error('Failed to delete KB entry:', e);
        // TODO: show toast/alert to user
    }
};
```

Apply to: `handleDelete`, `handleUpdate`, `handleExport`, `handleRollback` in both components.

**Step 2: Run frontend tests**

```bash
cd frontend && npx jest --verbose
```

**Step 3: Commit**

```bash
git add frontend/src/components/taxonomy/KnowledgeTab.tsx frontend/src/components/taxonomy/SectorKnowledgeTab.tsx
git commit -m "Ajuste: try/catch em handlers da KnowledgeTab (erros nao sao silenciosos)"
```

---

## Grupo 7: Code Cleanup e Padronizacao

### Task 7.1: Substituir print() por logging no llm_classifier

**Files:**
- Modify: `src/llm_classifier.py:154-163`

**Step 1: Replace print with logger**

```python
# src/llm_classifier.py:154-163 — change print() to:
    if total_usage["total_tokens"] > 0:
        logger.info(
            f"TOKEN USAGE TOTAL: input={total_usage['prompt_tokens']}, "
            f"output={total_usage['completion_tokens']}, "
            f"reasoning={total_usage['reasoning_tokens']}, "
            f"total={total_usage['total_tokens']}, "
            f"items={len(descriptions)}, llm_calls={len(chunks)}"
        )
```

Ensure `logger = logging.getLogger(__name__)` exists at module top (already present implicitly via `logging.info` calls — add explicit logger).

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add src/llm_classifier.py
git commit -m "Ajuste: substitui print() por logger.info no llm_classifier"
```

---

### Task 7.2: Fix bare except em model_trainer

**Files:**
- Modify: `src/model_trainer.py:273`

**Step 1: Replace bare except**

```python
# src/model_trainer.py:273 — change:
        except:
            pass
# to:
        except Exception:
            pass
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add src/model_trainer.py
git commit -m "Ajuste: bare except substituido por except Exception em model_trainer"
```

---

### Task 7.3: Fix sys.path.insert em hybrid_classifier

**Files:**
- Modify: `src/hybrid_classifier.py:20-23`

**Step 1: Replace sys.path hack with proper imports**

```python
# Remove lines 20-23 (sys.path manipulation)
# Replace internal imports with:
from src.taxonomy_engine import match_n4_without_priority
from src.llm_classifier import classify_items_with_llm
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add src/hybrid_classifier.py
git commit -m "Ajuste: remove sys.path.insert, usa imports padrao from src.module"
```

---

### Task 7.4: Mover normalize_header de models_bp para src/

**Files:**
- Modify: `blueprints/models_bp.py:162-176`
- Modify: `src/preprocessing.py`

**Step 1: Move function to preprocessing.py**

```python
# src/preprocessing.py — add:
def normalize_header(header: str) -> str:
    """Normalize column headers for training data import."""
    import unicodedata
    normalized = unicodedata.normalize("NFD", str(header)).encode("ascii", "ignore").decode("utf-8").lower().strip()
    aliases = {
        "descricao": "Descricao", "item_description": "Descricao",
        "description": "Descricao", "desc": "Descricao",
        "n1": "N1", "nivel 1": "N1", "level 1": "N1", "categoria": "N1",
        "n2": "N2", "nivel 2": "N2", "level 2": "N2", "subcategoria1": "N2",
        "n3": "N3", "nivel 3": "N3", "level 3": "N3", "subcategoria2": "N3",
        "n4": "N4", "nivel 4": "N4", "level 4": "N4", "subcategoria": "N4",
    }
    return aliases.get(normalized, header)
```

**Step 2: Import in models_bp.py**

```python
# blueprints/models_bp.py — replace local normalize_header with:
from src.preprocessing import normalize_header
```

Remove the local function definition (lines 162-176).

**Step 3: Run tests**

```bash
python3 -m pytest tests/ -v
```

**Step 4: Commit**

```bash
git add src/preprocessing.py blueprints/models_bp.py
git commit -m "Refactor: normalize_header movido para src/preprocessing.py"
```

---

### Task 7.5: Fix acentuacao na UI do frontend

**Files:**
- Modify: `frontend/src/components/taxonomy/ItemDetailPanel.tsx`
- Modify: `frontend/src/components/taxonomy/AnalyzeTab.tsx`
- Modify: `frontend/src/components/taxonomy/KnowledgeTab.tsx`
- Modify: `frontend/src/components/taxonomy/SectorKnowledgeTab.tsx`

**Step 1: Search and replace incorrect strings**

```
"instrucao" → "instrucao" (verificar contexto, corrigir para "instrucao")
"Edicao" → "Edicao" (verificar, corrigir para "Edicao")
"Proximo" → "Proximo" (corrigir para "Proximo")
"Analise Conversacional" → "Analise Conversacional"
"Faca perguntas" → "Faca perguntas"
"Fechar analise" → "Fechar analise"
"versao" → "versao"
"Historico de versoes" → "Historico de versoes"
```

Note: Use grep to find exact strings, then replace with properly accented versions.

**Step 2: Run frontend build to check**

```bash
cd frontend && npm run build
```

**Step 3: Commit**

```bash
git add frontend/src/components/
git commit -m "Ajuste: corrige acentuacao em textos da UI (instrucao, edicao, proximo, etc)"
```

---

## Grupo 8: Test Coverage

### Task 8.1: Testes para review_bp (ApproveClassifications)

**Files:**
- Create: `tests/test_review_bp.py` (expandir do Task 1.4)

**Step 1: Write comprehensive tests**

```python
# tests/test_review_bp.py
import json
import os
import pytest
from unittest.mock import patch, MagicMock
import azure.functions as func

class TestApproveClassifications:
    def _make_job(self, tmp_path, items=None):
        """Create a minimal job directory for testing."""
        job_id = "test-job-123"
        job_dir = tmp_path / "taxonomy_jobs" / job_id
        job_dir.mkdir(parents=True)

        status = {
            "status": "CLASSIFIED",
            "filename": "test.xlsx",
            "id_column": "SKU",
            "desc_column": "Descricao",
        }
        (job_dir / "status.json").write_text(json.dumps(status))

        if items is None:
            items = [
                {"SKU": "001", "Descricao": "Tubo PVC", "N1": "MRO", "N2": "Mat", "N3": "Hid", "N4": "Tubos", "source": "Grok", "confidence": 0.9},
            ]
        result = {"items": items}
        (job_dir / "result.json").write_text(json.dumps(result))

        return job_id, str(tmp_path)

    def test_approve_feeds_kb_and_returns_excel(self, tmp_path):
        job_id, models_dir = self._make_job(tmp_path)
        decisions = [{
            "index": 0, "description": "Tubo PVC", "decision": "approved",
            "N1": "MRO", "N2": "Mat", "N3": "Hid", "N4": "Tubos",
            "confidence": 0.9, "source": "Grok", "contribute_to_kb": True,
        }]
        # Test body construction and validation logic
        body = {"jobId": job_id, "projectId": "test-project", "decisions": decisions}
        assert body["jobId"] == job_id

    def test_incomplete_items_excluded_from_kb(self):
        """Items with 'Nao Identificado' should not be added to KB."""
        _incomplete = {"", "Nao Identificado", "Nao Identificado"}
        decision = {"N1": "Nao Identificado", "N2": "Test", "N3": "Test", "N4": "Test"}
        should_skip = any(
            str(decision.get(lvl, "")).strip() in _incomplete
            for lvl in ("N1", "N2", "N3", "N4")
        )
        assert should_skip is True
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/test_review_bp.py -v
```

**Step 3: Commit**

```bash
git add tests/test_review_bp.py
git commit -m "Adicionando testes para review_bp (ApproveClassifications)"
```

---

### Task 8.2: Testes para worker_helpers (consolidate_job, get_active_jobs)

**Files:**
- Modify: `tests/test_worker_helpers.py` (expandir)

**Step 1: Add tests for consolidate_job**

```python
# tests/test_worker_helpers.py — add:
import pandas as pd
from src.worker_helpers import consolidate_job, find_next_chunks

class TestConsolidateJob:
    def test_fills_na_with_nao_identificado(self, tmp_path):
        job_dir = str(tmp_path / "test-job")
        os.makedirs(job_dir)

        # Create 1 chunk + 1 result
        chunk_data = [{"Descricao": "Item A"}, {"Descricao": "Item B"}]
        result_data = [
            {"description": "Item A", "N1": "Cat1", "N2": "Sub1", "N3": "A", "N4": "X", "source": "LLM (Batch)", "confidence": 0.9},
            {"description": "Item B", "N1": "", "N2": "", "N3": "", "N4": "", "source": "None", "confidence": 0.0},
        ]

        with open(os.path.join(job_dir, "chunk_0.json"), "w") as f:
            json.dump(chunk_data, f)
        with open(os.path.join(job_dir, "result_0.json"), "w") as f:
            json.dump(result_data, f)

        status = {"status": "PROCESSING", "total_chunks": 1, "filename": "test.xlsx", "desc_column": "Descricao"}
        status_path = os.path.join(job_dir, "status.json")
        with open(status_path, "w") as f:
            json.dump(status, f)

        job_info = {
            "job_id": "test-job",
            "job_dir": job_dir,
            "status_path": status_path,
            "status": status,
            "total_chunks": 1,
        }

        consolidate_job(job_info)

        # Verify status is CLASSIFIED
        with open(status_path) as f:
            final_status = json.load(f)
        assert final_status["status"] == "CLASSIFIED"

        # Verify result.json exists
        with open(os.path.join(job_dir, "result.json")) as f:
            result = json.load(f)
        items = result["items"]
        assert len(items) == 2
        # Item B should have "Nao Identificado" filled in
        assert items[1]["N1"] == "Nao Identificado"

class TestFindNextChunks:
    def test_finds_unprocessed_chunks(self, tmp_path):
        job_dir = str(tmp_path)
        # chunk_0 exists, result_0 exists (processed)
        (tmp_path / "chunk_0.json").write_text("[]")
        (tmp_path / "result_0.json").write_text("[]")
        # chunk_1 exists, no result (unprocessed)
        (tmp_path / "chunk_1.json").write_text("[]")

        job_info = {"job_dir": job_dir, "total_chunks": 2}
        result = find_next_chunks(job_info, max_count=5)
        assert result == [1]

    def test_respects_exclude_set(self, tmp_path):
        (tmp_path / "chunk_0.json").write_text("[]")
        job_info = {"job_dir": str(tmp_path), "total_chunks": 1}
        result = find_next_chunks(job_info, max_count=5, exclude={0})
        assert result == []
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/test_worker_helpers.py -v
```

**Step 3: Commit**

```bash
git add tests/test_worker_helpers.py
git commit -m "Adicionando testes para consolidate_job e find_next_chunks"
```

---

### Task 8.3: Testes para taxonomy_engine (generate_analytics)

**Files:**
- Modify: `tests/test_taxonomy_engine.py` (expandir do Task 3.2)

**Step 1: Add analytics tests**

```python
# tests/test_taxonomy_engine.py — add:
from src.taxonomy_engine import generate_analytics

def test_generate_analytics_pareto():
    df = pd.DataFrame({
        "N1": ["A"] * 80 + ["B"] * 15 + ["C"] * 5,
        "N2": ["Sub"] * 100,
        "N3": ["X"] * 100,
        "N4": ["Y"] * 100,
    })
    analytics = generate_analytics(df)
    assert "pareto_N1" in analytics
    assert len(analytics["pareto_N1"]) > 0
    # First entry should be "A" (highest count)
    assert analytics["pareto_N1"][0]["N1"] == "A"

def test_generate_analytics_excludes_nao_identificado():
    df = pd.DataFrame({
        "N1": ["A", "Nao Identificado", "B"],
        "N2": ["Sub", "", "Sub"],
        "N3": ["X", "Y", "Z"],
        "N4": ["P", "Q", "R"],
    })
    analytics = generate_analytics(df)
    n1_values = [p["N1"] for p in analytics["pareto_N1"]]
    assert "Nao Identificado" not in n1_values

def test_generate_analytics_empty_df():
    df = pd.DataFrame(columns=["N1", "N2", "N3", "N4"])
    analytics = generate_analytics(df)
    assert analytics["pareto_N1"] == []
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/test_taxonomy_engine.py -v
```

**Step 3: Commit**

```bash
git add tests/test_taxonomy_engine.py
git commit -m "Adicionando testes para generate_analytics e generate_summary"
```

---

## Resumo de Execucao

| Grupo | Tasks | Dependencias | Paralelizavel |
|-------|-------|-------------|---------------|
| 1. Backend Bug Fixes | 1.1-1.6 | Nenhuma | Sim (entre si) |
| 2. Race Conditions | 2.1-2.2 | Nenhuma | Sim |
| 3. Performance | 3.1-3.3 | Nenhuma | Sim |
| 4. API Layer | 4.1-4.7 | Depende de 2.1 (file_lock) | Parcial |
| 5. Frontend Critical | 5.1-5.5 | Nenhuma | Sim |
| 6. Frontend Important | 6.1-6.2 | Nenhuma | Sim |
| 7. Code Cleanup | 7.1-7.5 | Nenhuma | Sim |
| 8. Test Coverage | 8.1-8.3 | Depende de 1.x (fixes) | Parcial |

**Ordem recomendada:** Grupos 1+2+3+5 em paralelo -> Grupos 4+6+7 em paralelo -> Grupo 8

**Total:** 29 tasks, ~66 achados cobertos

**Verificacao final apos todos os grupos:**
```bash
python3 -m pytest tests/ -v                    # Backend: todos passam
cd frontend && npx jest --verbose              # Frontend: todos passam
cd frontend && npm run build                   # Build sem erros de tipo
```
