# Correções de Escalabilidade e Estabilidade — Plano de Implementação

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir todos os itens CRITICAL e HIGH identificados na revisão arquitetural, eliminando riscos de perda de dados, double-processing, e instabilidade sob carga.

**Architecture:** Sete correções incrementais e independentes. Cada task produz código testável sem depender das outras. A estratégia é: (1) adicionar file locking na KB, (2) proteger ApproveClassifications com locked_status, (3) ajustar timeouts no host.json, (4) adicionar poison queue trigger, (5) otimizar consolidação, (6) adicionar rate limiter global no LLM, (7) tratar filelock.Timeout nos endpoints HTTP.

**Tech Stack:** Python 3.9+, Azure Functions v2, filelock, threading.Semaphore, pytest

---

## Mapa de Arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|------------------|
| `src/knowledge_base.py` | Modificar | Adicionar FileLock em `save()` e `_load()` |
| `src/file_lock.py` | Modificar | Expor constante `_LOCK_TIMEOUT` e adicionar helper genérico |
| `blueprints/review_bp.py` | Modificar | Usar `locked_status()` no ApproveClassifications |
| `host.json` | Modificar | Ajustar visibilityTimeout > functionTimeout |
| `blueprints/worker_bp.py` | Modificar | Adicionar poison queue trigger |
| `src/worker_helpers.py` | Modificar | Otimizar consolidação (streaming, separar Excel) |
| `src/llm_classifier.py` | Modificar | Adicionar rate limiter global (Semaphore) |
| `src/api_helpers.py` | Modificar | Catch `filelock.Timeout` → 503 |
| `tests/test_knowledge_base.py` | Modificar | Testes de concorrência KB |
| `tests/test_review_bp.py` | Modificar | Teste do ApproveClassifications com lock |
| `tests/test_worker_helpers.py` | Modificar | Testes de consolidação otimizada |
| `tests/test_llm_classifier.py` | Modificar | Teste do rate limiter |
| `tests/test_api_helpers.py` | Modificar | Teste do catch de filelock.Timeout |
| `tests/test_worker_bp.py` | Criar | Teste do poison queue trigger |

---

## Task 1: FileLock na Knowledge Base (C1)

**Files:**
- Modify: `src/knowledge_base.py:35-43` (`save`, `_load`), `:53-119` (`add_entries`), `:121-128` (`update_entry`), `:130-136` (`delete_entry`)
- Modify: `tests/test_knowledge_base.py`

### Contexto

`KnowledgeBase.save()` escreve `knowledge_base.json` sem lock. Duas requests concorrentes (ex: `ApproveClassifications` + `AddKBEntry`) podem causar last-write-wins, perdendo entradas. A solução é aplicar `filelock.FileLock` em todas as operações de mutação com padrão atômico: acquire lock → reload from disk → mutate in-memory → write → release. O `_load()` e `save()` recebem lock individual, mas `add_entries()`, `update_entry()` e `delete_entry()` precisam de lock atômico cobrindo todo o ciclo read-modify-write.

**NOTA:** `rollback_to_version()` (linha 203) também muta `self.entries` e chama `save()` sem lock. Considerar aplicar o mesmo padrão, mas é operação de baixa frequência — pode ficar como follow-up.

- [ ] **Step 1: Escrever teste de concorrência KB**

Adicionar em `tests/test_knowledge_base.py`:

```python
import threading
import os

class TestKBConcurrency:
    def test_concurrent_add_entries_no_data_loss(self, tmp_path):
        """Two concurrent add_entries calls must not lose entries."""
        # Setup: create empty KB on disk first
        make_kb(tmp_path, initial_entries=[])

        entries_a = [_entry("Parafuso M8", "Fixadores", N1="MRO")]
        entries_b = [_entry("Válvula gaveta", "Válvulas", N1="Industrial")]

        barrier = threading.Barrier(2)
        errors = []

        def add_a():
            try:
                barrier.wait(timeout=5)
                # Each thread creates its own KnowledgeBase instance (simulates separate requests)
                kb_a = KnowledgeBase("test-project", str(tmp_path))
                kb_a.add_entries(entries_a)
            except Exception as e:
                errors.append(e)

        def add_b():
            try:
                barrier.wait(timeout=5)
                kb_b = KnowledgeBase("test-project", str(tmp_path))
                kb_b.add_entries(entries_b)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=add_a)
        t2 = threading.Thread(target=add_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        final_kb = KnowledgeBase("test-project", str(tmp_path))
        assert len(final_kb.entries) == 2, (
            f"Expected 2 entries, got {len(final_kb.entries)} — concurrent write lost data"
        )

    def test_save_uses_file_lock(self, tmp_path):
        """save() must acquire a lock on knowledge_base.json.lock."""
        kb = make_kb(tmp_path, initial_entries=[])
        kb.add_entries([_entry("Teste lock", "Fixadores")])
        lock_path = kb.kb_path + ".lock"
        assert os.path.exists(lock_path), "File lock sidecar not created"
```

- [ ] **Step 2: Rodar testes para verificar que falham**

Run: `python3 -m pytest tests/test_knowledge_base.py::TestKBConcurrency -v`
Expected: FAIL — `test_concurrent_add_entries_no_data_loss` falha intermitentemente, `test_save_uses_file_lock` falha (lock sidecar não existe).

- [ ] **Step 3: Implementar FileLock atômico em todas as operações de mutação**

Em `src/knowledge_base.py`, adicionar import no topo:

```python
from filelock import FileLock

_KB_LOCK_TIMEOUT = 10  # seconds
```

Substituir `_load()` (linha 35) e `save()` (linha 41):

```python
def _load(self) -> List[KBEntryDict]:
    if os.path.exists(self.kb_path):
        lock = FileLock(self.kb_path + ".lock", timeout=_KB_LOCK_TIMEOUT)
        with lock:
            with open(self.kb_path, "r", encoding="utf-8") as f:
                return json.load(f)
    return []

def save(self) -> None:
    lock = FileLock(self.kb_path + ".lock", timeout=_KB_LOCK_TIMEOUT)
    with lock:
        with open(self.kb_path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)
```

Refatorar `add_entries()` (linha 53) — o lock DEVE cobrir reload + dedup + write:

```python
def add_entries(self, entries: List[KBEntryDict]) -> int:
    """Add entries to KB with atomic read-modify-write under file lock."""
    lock = FileLock(self.kb_path + ".lock", timeout=_KB_LOCK_TIMEOUT)
    with lock:
        # CRITICAL: reload from disk inside the lock to prevent stale reads.
        # Two concurrent callers each load a snapshot in __init__(); without
        # this reload, the second writer's add_entries() would overwrite
        # the first writer's entries (last-write-wins).
        if os.path.exists(self.kb_path):
            with open(self.kb_path, "r", encoding="utf-8") as f:
                self.entries = json.load(f)

        # Build lookup of existing entries AFTER reload (must use fresh data)
        existing = {e["description_norm"]: i for i, e in enumerate(self.entries)}
        added = 0
        now = datetime.now(timezone.utc).isoformat()
        version = self._current_version()

        source_rank = {"consultant_correction": 2, "reclassified_with_guidance": 1, "llm_approved": 0}

        for entry in entries:
            if any(
                str(entry.get(lvl, "")).strip() in INCOMPLETE_VALUES
                for lvl in ("N1", "N2", "N3", "N4")
            ):
                continue
            desc = str(entry.get("description", ""))
            desc_norm = self._normalize(desc)
            new_source = entry.get("source", "llm_approved")

            new_entry = {
                "id": str(uuid.uuid4()),
                "description": desc,
                "description_norm": desc_norm,
                "N1": entry.get("N1", ""),
                "N2": entry.get("N2", ""),
                "N3": entry.get("N3", ""),
                "N4": entry.get("N4", ""),
                "source": new_source,
                "confidence": float(entry.get("confidence", 0.85)),
                "instruction_used": entry.get("instruction_used"),
                "version": version,
                "date_added": now,
            }

            if desc_norm in existing:
                idx = existing[desc_norm]
                old = self.entries[idx]
                old_source = old.get("source", "llm_approved")
                old_rank = source_rank.get(old_source, 0)
                new_rank = source_rank.get(new_source, 0)
                classification_changed = any(
                    old.get(f, "") != new_entry.get(f, "")
                    for f in ("N1", "N2", "N3", "N4")
                )
                if new_rank > old_rank or (new_rank == old_rank and classification_changed):
                    preserved_id = old["id"]
                    self.entries[idx].update(new_entry)
                    self.entries[idx]["id"] = preserved_id
                    added += 1
            else:
                self.entries.append(new_entry)
                existing[desc_norm] = len(self.entries) - 1
                added += 1

        if added > 0:
            with open(self.kb_path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, ensure_ascii=False, indent=2)
    return added
```

Refatorar `update_entry()` (linha 121) — mesmo padrão atômico:

```python
def update_entry(self, entry_id: str, data: Dict[str, object]) -> bool:
    lock = FileLock(self.kb_path + ".lock", timeout=_KB_LOCK_TIMEOUT)
    with lock:
        # Reload from disk inside lock
        if os.path.exists(self.kb_path):
            with open(self.kb_path, "r", encoding="utf-8") as f:
                self.entries = json.load(f)
        for i, e in enumerate(self.entries):
            if e["id"] == entry_id:
                self.entries[i].update(data)
                self.entries[i]["id"] = entry_id
                with open(self.kb_path, "w", encoding="utf-8") as f:
                    json.dump(self.entries, f, ensure_ascii=False, indent=2)
                return True
    return False
```

Refatorar `delete_entry()` (linha 130) — mesmo padrão atômico:

```python
def delete_entry(self, entry_id: str) -> bool:
    lock = FileLock(self.kb_path + ".lock", timeout=_KB_LOCK_TIMEOUT)
    with lock:
        if os.path.exists(self.kb_path):
            with open(self.kb_path, "r", encoding="utf-8") as f:
                self.entries = json.load(f)
        original_len = len(self.entries)
        self.entries = [e for e in self.entries if e["id"] != entry_id]
        if len(self.entries) < original_len:
            with open(self.kb_path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, ensure_ascii=False, indent=2)
            return True
    return False
```

- [ ] **Step 4: Rodar testes para verificar que passam**

Run: `python3 -m pytest tests/test_knowledge_base.py -v`
Expected: PASS — todos os testes existentes + novos de concorrência.

- [ ] **Step 5: Rodar suite completa para regressão**

Run: `python3 -m pytest tests/ -v`
Expected: PASS — 297+ testes.

- [ ] **Step 6: Commit**

```bash
git add src/knowledge_base.py tests/test_knowledge_base.py
git commit -m "Fix: FileLock na KnowledgeBase — previne perda de dados em writes concorrentes"
```

---

## Task 2: locked_status no ApproveClassifications (C2)

**Files:**
- Modify: `blueprints/review_bp.py:14` (adicionar import `locked_status`), `:13` (adicionar import `ConflictError`), `:116-274` (lógica do endpoint)
- Modify: `tests/test_review_bp.py`

### Contexto

`ApproveClassifications` lê `status.json` na linha 196 e escreve na linha 260 sem manter lock entre as operações. Duas aprovações simultâneas do mesmo job criam entradas KB duplicadas e sobrescrevem o status. A solução é usar `locked_status()` para a transição de status, com guard de estado.

**Pré-requisito de imports:** A linha 14 atual importa `read_status, write_status` — precisa adicionar `locked_status`. A linha 13 importa `NotFoundError, ValidationError` — precisa adicionar `ConflictError`.

**Nota sobre exceções dentro de `locked_status`:** O `@contextmanager` de `file_lock.py` NÃO escreve o arquivo de volta quando uma exceção é levantada no `yield`. Se `ConflictError` for raised dentro do `with locked_status()`, o status NÃO é modificado (comportamento correto). O guard dentro do lock usa `return error_response(...)` ao invés de `raise` para ser explícito sobre o fluxo.

- [ ] **Step 1: Escrever teste de guard de status**

Adicionar em `tests/test_review_bp.py`:

```python
def test_approve_rejects_if_not_classified(self, tmp_path, mock_req):
    """ApproveClassifications deve rejeitar se status não é CLASSIFIED."""
    # Arrange: job já COMPLETED
    job_dir = tmp_path / "taxonomy_jobs" / "job-already-done"
    job_dir.mkdir(parents=True)
    status_path = job_dir / "status.json"
    status_path.write_text(json.dumps({
        "status": "COMPLETED", "filename": "test.xlsx"
    }))
    # Act + Assert: deve retornar 409 Conflict
    # (testar via chamada direta ao endpoint com mock)
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_review_bp.py::test_approve_rejects_if_not_classified -v`
Expected: FAIL — endpoint não faz guard de status.

- [ ] **Step 3: Implementar locked_status no ApproveClassifications**

Em `blueprints/review_bp.py`:

1. **Atualizar imports** (linhas 13-14 — ambas precisam de modificação):
```python
from src.file_lock import read_status, write_status, locked_status
from src.exceptions import NotFoundError, ValidationError, ConflictError
```

2. Substituir o bloco de leitura de status (linha 196) e escrita (linhas 240-260):

```python
    # 2. Generate approved Excel from decisions
    import pandas as pd

    # Load status under lock to prevent concurrent approvals
    status_path = os.path.join(job_dir, "status.json")

    # Read status for the Excel generation (read-only, outside lock)
    status_data = read_status(status_path)
    current = status_data.get("status", "")
    if current not in ("CLASSIFIED", "APPROVED"):
        raise ConflictError(
            f"Job {job_id} has status '{current}' — only CLASSIFIED or APPROVED jobs can be approved"
        )

    id_col = status_data.get("id_column")
    extra_columns = status_data.get("extra_columns", [])
    # ... (lógica de Excel inalterada) ...

    # 3. Update job status — atomic transition under lock
    download_filename = None
    with locked_status(status_path) as locked_data:
        # Re-check status inside lock (could have changed between read and lock acquisition)
        if locked_data.get("status") not in ("CLASSIFIED", "APPROVED"):
            # NOTE: Raising inside @contextmanager skips the write-back (correct behavior).
            raise ConflictError(
                f"Job {job_id} status changed to '{locked_data.get('status')}' during approval"
            )
        locked_data["status"] = "COMPLETED"
        locked_data["review_completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        locked_data["review_summary"] = {
            "total": len(decisions),
            "approved": approved_count,
            "edited": edited_count,
            "rejected": rejected_count,
            "kb_added": kb_added,
        }
        original_filename = locked_data.get("filename", "upload.xlsx")
        base_name = os.path.splitext(original_filename)[0]
        download_filename = f"{base_name}_classificado.xlsx"
        locked_data["approved_download_filename"] = download_filename

    # Salvar base64 em arquivo separado (fora do lock — escrita idempotente)
    approved_path = os.path.join(job_dir, "approved_result_b64.txt")
    with open(approved_path, "w", encoding="utf-8") as af:
        af.write(file_b64)
```

- [ ] **Step 4: Rodar testes para verificar que passam**

Run: `python3 -m pytest tests/test_review_bp.py -v`
Expected: PASS.

- [ ] **Step 5: Rodar suite completa**

Run: `python3 -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add blueprints/review_bp.py tests/test_review_bp.py
git commit -m "Fix: locked_status no ApproveClassifications — previne aprovação duplicada"
```

---

## Task 3: visibilityTimeout > functionTimeout (H1)

**Files:**
- Modify: `host.json:16`

### Contexto

`functionTimeout` e `visibilityTimeout` estão ambos em 30 min. Se o processamento levar exatamente 30 min, a mensagem fica visível na queue antes do worker terminar, causando double-processing. Solução: `visibilityTimeout = 45min` > `functionTimeout = 30min`.

- [ ] **Step 1: Modificar host.json**

**NOTA:** O bloco `queues` está DENTRO de `extensions` (não no top-level). Alterar apenas o valor de `visibilityTimeout` dentro de `extensions.queues`:

```json
"extensions": {
    "http": { ... },
    "queues": {
        "maxPollingInterval": "00:00:05",
        "visibilityTimeout": "00:45:00",
        "batchSize": 1,
        "maxDequeueCount": 5,
        "newBatchThreshold": 0,
        "messageEncoding": "none"
    }
}
```

Única mudança: `"visibilityTimeout": "00:30:00"` → `"visibilityTimeout": "00:45:00"`.

- [ ] **Step 2: Validar JSON**

Run: `python3 -c "import json; json.load(open('host.json'))"`
Expected: sem erros.

- [ ] **Step 3: Commit**

```bash
git add host.json
git commit -m "Fix: visibilityTimeout (45min) > functionTimeout (30min) — previne double-processing"
```

---

## Task 4: Otimizar consolidação — reduzir pico de memória (H2)

**Files:**
- Modify: `src/worker_helpers.py:496-511` (consolidate_job — separar Excel b64 do result.json)
- Modify: `tests/test_worker_helpers.py:449-478` (atualizar teste existente `test_result_json_contains_excel_base64`)

### Contexto

`consolidate_job()` mantém múltiplas representações do dataset completo em memória simultaneamente: `results_accumulated` (list), `original_chunks` (list), 2 DataFrames, Excel BytesIO, base64 string, e `result.json` string. Para 13.638 linhas, o pico é ~200-400 MB. A principal otimização é separar `fileContent` (Excel b64) do `result.json`, salvando-o em `classified_excel_b64.txt`, e liberar buffers intermediários com `del` logo após o uso.

**NOTA IMPORTANTE sobre consumidores de `fileContent`:**
- `DownloadJobExcel` (classification_bp.py:509-611) NÃO lê `fileContent` do `result.json`. Ele gera o Excel on-the-fly a partir dos `items`. Portanto, NÃO precisa de fallback.
- `GetTaxonomyJobStatus` (classification_bp.py:300-304) faz `response.update(json.load(rf))` para jobs COMPLETED, o que copiava `fileContent` para a resposta HTTP (~10-15 MB!). Com esta mudança, o `fileContent` sai da resposta — **isto é uma melhoria** pois o frontend não usa esse campo do status poll (usa `DownloadJobExcel` para baixar).
- O frontend (`useTaxonomySession.ts:154`) lê `status.file_content_base64`, mas isto vem do `ApproveClassifications` response (review_bp.py:273), não do `result.json`. Então não é afetado.

**Teste existente que QUEBRA:** `test_result_json_contains_excel_base64` (test_worker_helpers.py:449-478) asserta `"fileContent" in result`. Este teste DEVE ser atualizado para verificar o novo arquivo `classified_excel_b64.txt`.

- [ ] **Step 1: Atualizar teste existente e adicionar novo**

Em `tests/test_worker_helpers.py`, **substituir** `test_result_json_contains_excel_base64` (linhas 449-478):

```python
    def test_result_json_does_not_contain_excel_base64(self, tmp_path):
        """result.json NÃO deve conter fileContent — Excel b64 fica em classified_excel_b64.txt."""
        chunk_data = [{"Descricao": "Item A"}]
        result_data = [
            {
                "description": "Item A",
                "N1": "Cat1",
                "N2": "S1",
                "N3": "A",
                "N4": "X",
                "source": "LLM (Batch)",
                "confidence": 0.9,
            },
        ]

        job_info = self._make_job(tmp_path, "test-excel", [chunk_data], [result_data])
        consolidate_job(job_info)

        # result.json NÃO deve ter fileContent
        with open(
            os.path.join(job_info["job_dir"], "result.json"), encoding="utf-8"
        ) as f:
            result = json.load(f)
        assert "fileContent" not in result, "Excel b64 should NOT be in result.json"

        # Excel b64 deve estar em arquivo separado
        import base64
        excel_path = os.path.join(job_info["job_dir"], "classified_excel_b64.txt")
        assert os.path.exists(excel_path), "classified_excel_b64.txt not found"
        excel_b64 = open(excel_path, "r").read()
        assert len(excel_b64) > 100, "Excel b64 file is too small"
        decoded = base64.b64decode(excel_b64)
        assert len(decoded) > 0, "Excel b64 decodes to empty"
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_worker_helpers.py::TestConsolidateJob::test_result_json_does_not_contain_excel_base64 -v`
Expected: FAIL — `fileContent` ainda está no `result.json`.

- [ ] **Step 3: Implementar consolidação otimizada**

Em `src/worker_helpers.py`, modificar `consolidate_job()` (linhas 496-511). Substituir:

```python
    # Generate Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        final_df.to_excel(writer, index=False, sheet_name="Classificação")
    output.seek(0)
    xlsx_b64 = base64.b64encode(output.getvalue()).decode("utf-8")

    final_result = {
        "items": final_df.to_dict(orient="records"),
        "analytics": analytics,
        "summary": summary,
        "fileContent": xlsx_b64,
        "filename": f"classified_{status['filename']}",
    }

    with open(os.path.join(job_dir, "result.json"), "w") as f:
        f.write(safe_json_dumps(final_result))
```

Por:

```python
    # Generate Excel — salvar em arquivo separado (não no result.json)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        final_df.to_excel(writer, index=False, sheet_name="Classificação")
    output.seek(0)
    xlsx_b64 = base64.b64encode(output.getvalue()).decode("utf-8")
    del output  # liberar BytesIO imediatamente

    # Salvar Excel b64 em arquivo separado (reduz result.json de ~15MB para ~5MB)
    excel_b64_path = os.path.join(job_dir, "classified_excel_b64.txt")
    with open(excel_b64_path, "w", encoding="utf-8") as ef:
        ef.write(xlsx_b64)
    del xlsx_b64  # liberar string b64

    # Gerar result.json SEM fileContent
    final_result = {
        "items": final_df.to_dict(orient="records"),
        "analytics": analytics,
        "summary": summary,
        "filename": f"classified_{status['filename']}",
    }

    # Liberar DataFrame antes de serializar
    del final_df

    with open(os.path.join(job_dir, "result.json"), "w") as f:
        f.write(safe_json_dumps(final_result))
```

**NÃO modificar `DownloadJobExcel` nem `classification_bp.py`** — nenhum endpoint lê `fileContent` do `result.json`.

- [ ] **Step 4: Rodar testes**

Run: `python3 -m pytest tests/test_worker_helpers.py -v`
Expected: PASS — o teste atualizado verifica o novo arquivo separado.

- [ ] **Step 5: Rodar suite completa**

Run: `python3 -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/worker_helpers.py tests/test_worker_helpers.py
git commit -m "Refactor: consolidação otimizada — Excel b64 em arquivo separado, libera memória cedo"
```

---

## Task 5: Poison Queue Trigger — erro visível imediatamente (H3)

**Files:**
- Modify: `blueprints/worker_bp.py`
- Create: `tests/test_worker_bp.py`

### Contexto

Quando o worker falha 5x (maxDequeueCount), a mensagem vai para `taxonomy-jobs-poison`. O job fica em `PROCESSING` até o cleanup timer rodar (até 1 hora depois). Solução: adicionar um trigger na poison queue que marca o job como `ERROR` imediatamente.

- [ ] **Step 1: Escrever teste do poison queue handler**

Criar `tests/test_worker_bp.py`:

```python
"""Tests for blueprints/worker_bp.py — queue triggers."""
import json
import os
import pytest
from unittest.mock import MagicMock, patch

from src.file_lock import write_status, read_status


class TestHandlePoisonMessage:
    def test_marks_job_as_error(self, tmp_path, monkeypatch):
        """Poison queue handler must mark the job as ERROR."""
        monkeypatch.setattr("src.utils.get_jobs_dir", lambda: str(tmp_path))

        job_dir = tmp_path / "poison-job-123"
        job_dir.mkdir()
        status_path = str(job_dir / "status.json")
        write_status(status_path, {"status": "PROCESSING", "filename": "test.xlsx"})

        from blueprints.worker_bp import _handle_poison_message
        _handle_poison_message("poison-job-123")

        result = read_status(status_path)
        assert result["status"] == "ERROR"
        assert "poison" in result.get("error", "").lower()

    def test_ignores_already_cancelled(self, tmp_path, monkeypatch):
        """Poison handler should not overwrite CANCELLED status."""
        monkeypatch.setattr("src.utils.get_jobs_dir", lambda: str(tmp_path))

        job_dir = tmp_path / "cancelled-job"
        job_dir.mkdir()
        status_path = str(job_dir / "status.json")
        write_status(status_path, {"status": "CANCELLED"})

        from blueprints.worker_bp import _handle_poison_message
        _handle_poison_message("cancelled-job")

        result = read_status(status_path)
        assert result["status"] == "CANCELLED"
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_worker_bp.py -v`
Expected: FAIL — `_handle_poison_message` não existe.

- [ ] **Step 3: Implementar poison queue trigger**

Em `blueprints/worker_bp.py`:

```python
@worker_bp.queue_trigger(
    arg_name="msg",
    queue_name="taxonomy-jobs-poison",
    connection="AzureWebJobsStorage",
)
def HandlePoisonTaxonomyJob(msg: func.QueueMessage) -> None:
    """Poison queue trigger: marks failed jobs as ERROR immediately.

    When a job message fails maxDequeueCount times, Azure moves it to
    taxonomy-jobs-poison. This trigger picks it up and writes ERROR status
    so the frontend shows the failure instantly instead of waiting for
    the hourly cleanup timer.
    """
    try:
        payload = json.loads(msg.get_body().decode("utf-8"))
        job_id = payload["job_id"]
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[PoisonHandler] Mensagem inválida: {e}")
        return

    logger.warning(f"[PoisonHandler] Job {job_id} na poison queue — marcando ERROR")
    _handle_poison_message(job_id)


def _handle_poison_message(job_id: str) -> None:
    """Mark a job as ERROR after exhausting queue retries."""
    from src.utils import get_jobs_dir
    from src.file_lock import locked_status

    jobs_root = get_jobs_dir()
    job_dir = os.path.join(jobs_root, job_id)
    status_path = os.path.join(job_dir, "status.json")

    if not os.path.exists(status_path):
        logger.warning(f"[PoisonHandler] Job {job_id} não encontrado")
        return

    with locked_status(status_path) as data:
        current = data.get("status", "")
        if current in ("CANCELLED", "COMPLETED", "CLASSIFIED", "ERROR"):
            logger.info(f"[PoisonHandler] Job {job_id} já em '{current}' — ignorando")
            return
        data["status"] = "ERROR"
        data["error"] = (
            "Job falhou após múltiplas tentativas de processamento (poison queue). "
            "Verifique os logs do worker para detalhes."
        )
        data["error_at"] = datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Rodar testes**

Run: `python3 -m pytest tests/test_worker_bp.py -v`
Expected: PASS.

- [ ] **Step 5: Rodar suite completa**

Run: `python3 -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add blueprints/worker_bp.py tests/test_worker_bp.py
git commit -m "Fix: poison queue trigger marca ERROR imediatamente — erro visível sem esperar 1h"
```

---

## Task 6: Rate Limiter Global para chamadas LLM (H4)

**Files:**
- Modify: `src/llm_classifier.py:1-20, 80-135`
- Modify: `tests/test_llm_classifier.py`

### Contexto

Cada chunk de 500 itens gera 5 chamadas LLM paralelas. Com `MAX_PARALLEL_CHUNKS=5`, são até 25 chamadas simultâneas ao Grok. Se a API retorna 429, todos os 25 threads retentam ao mesmo tempo (thundering herd). Solução: `threading.Semaphore` global que limita chamadas concorrentes.

- [ ] **Step 1: Escrever teste do rate limiter**

Adicionar em `tests/test_llm_classifier.py`:

```python
import threading
from src.llm_classifier import _LLM_SEMAPHORE, LLM_MAX_CONCURRENT_CALLS

class TestRateLimiter:
    def test_semaphore_limits_concurrency(self):
        """LLM semaphore must limit concurrent API calls."""
        assert isinstance(_LLM_SEMAPHORE, threading.Semaphore)
        # Verify the bound matches the constant
        assert LLM_MAX_CONCURRENT_CALLS <= 10, (
            "Max concurrent LLM calls should be ≤ 10 to avoid thundering herd"
        )

    def test_semaphore_is_module_level(self):
        """Semaphore must be module-level (shared across all ThreadPoolExecutors)."""
        from src import llm_classifier
        assert hasattr(llm_classifier, '_LLM_SEMAPHORE')
        # Same object across imports
        from src.llm_classifier import _LLM_SEMAPHORE as s2
        assert _LLM_SEMAPHORE is s2
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_llm_classifier.py::TestRateLimiter -v`
Expected: FAIL — `_LLM_SEMAPHORE` não existe.

- [ ] **Step 3: Implementar rate limiter**

Em `src/llm_classifier.py`:

```python
# No topo, após imports existentes:
import threading

LLM_MAX_CONCURRENT_CALLS = 8  # Max chamadas LLM simultâneas (global, cross-chunk)
_LLM_SEMAPHORE = threading.Semaphore(LLM_MAX_CONCURRENT_CALLS)
```

Modificar `_call_openai_api()` para usar o semaphore. Envolver o bloco de retry inteiro:

```python
def _call_openai_api(
    items: List[str],
    config: Dict[str, str],
    # ... (params iguais) ...
) -> List[ClassificationResultDict]:
    """Helper to call the API for a chunk of items."""

    # Acquire semaphore BEFORE making the API call
    _LLM_SEMAPHORE.acquire()
    try:
        # ... (todo o corpo existente da função) ...
    finally:
        _LLM_SEMAPHORE.release()
```

Reduzir `ThreadPoolExecutor(max_workers=20)` para `max_workers=LLM_MAX_CONCURRENT_CALLS` em `classify_items_with_llm()` (linha 127), já que o semaphore é o gargalo real:

```python
    with ThreadPoolExecutor(max_workers=LLM_MAX_CONCURRENT_CALLS) as executor:
```

**NOTA:** `map_categories_with_llm()` (linha 479) também usa `ThreadPoolExecutor(max_workers=20)` mas NÃO passa pelo semaphore. Para consistência, aplicar o mesmo padrão:
- Usar `_LLM_SEMAPHORE` no requests.post dentro do loop de `map_categories_with_llm`, OU
- Reduzir `max_workers` para `LLM_MAX_CONCURRENT_CALLS` nessa função também.

A segunda opção é mais simples e suficiente (essa função é raramente chamada).

- [ ] **Step 4: Rodar testes**

Run: `python3 -m pytest tests/test_llm_classifier.py -v`
Expected: PASS.

- [ ] **Step 5: Rodar suite completa**

Run: `python3 -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llm_classifier.py tests/test_llm_classifier.py
git commit -m "Fix: rate limiter global (Semaphore) nas chamadas LLM — previne thundering herd"
```

---

## Task 7: Catch filelock.Timeout nos endpoints HTTP (H5)

**Files:**
- Modify: `src/api_helpers.py:49-80`
- Modify: `tests/test_api_helpers.py`

### Contexto

Se o worker segura o lock do `status.json` por mais de 10s (carga alta), `read_status()` levanta `filelock.Timeout`. O `@handle_errors` mapeia isso para 500 genérico, quando deveria ser 503 (Service Unavailable) com `Retry-After` header.

- [ ] **Step 1: Escrever teste do catch de filelock.Timeout**

Adicionar em `tests/test_api_helpers.py`:

```python
from filelock import Timeout as FileLockTimeout

def test_handle_errors_catches_filelock_timeout():
    """filelock.Timeout should return 503 with Retry-After header."""
    @handle_errors("TestEndpoint")
    def endpoint(req):
        raise FileLockTimeout("status.json.lock")

    resp = endpoint(None)
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "2"
    body = json.loads(resp.get_body())
    assert "lock" in body["error"].lower() or "ocupado" in body["error"].lower()
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_api_helpers.py::test_handle_errors_catches_filelock_timeout -v`
Expected: FAIL — retorna 500 ao invés de 503.

- [ ] **Step 3: Implementar catch de filelock.Timeout**

Em `src/api_helpers.py`, adicionar import e novo branch no `@handle_errors`:

```python
from filelock import Timeout as FileLockTimeout

def handle_errors(func_or_name=None):
    def decorator(fn):
        endpoint_name = func_or_name if isinstance(func_or_name, str) else fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except FileLockTimeout:
                logger.warning(f"{endpoint_name}: file lock timeout — recurso ocupado")
                return func.HttpResponse(
                    body=json.dumps({"error": "Recurso temporariamente ocupado. Tente novamente."}, ensure_ascii=False),
                    status_code=503,
                    mimetype="application/json",
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Retry-After": "2",
                    },
                )
            except SpendAnalysisError as e:
                logger.warning(f"{endpoint_name}: {e}")
                return error_response(str(e), e.status_code)
            except ValueError as e:
                logger.warning(f"{endpoint_name} validation error: {e}")
                return error_response(str(e), 400)
            except Exception as e:
                logger.error(f"{endpoint_name} error: {e}", exc_info=True)
                return error_response(str(e), 500)

        return wrapper

    if callable(func_or_name):
        return decorator(func_or_name)
    return decorator
```

**IMPORTANTE:** O catch de `FileLockTimeout` deve vir ANTES de `Exception` para não ser engolido pelo catch-all.

- [ ] **Step 4: Rodar testes**

Run: `python3 -m pytest tests/test_api_helpers.py -v`
Expected: PASS.

- [ ] **Step 5: Rodar suite completa**

Run: `python3 -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/api_helpers.py tests/test_api_helpers.py
git commit -m "Fix: catch filelock.Timeout → 503 com Retry-After — polling não quebra sob carga"
```

---

## Ordem de Execução Recomendada

As tasks são independentes, mas a ordem sugerida minimiza riscos:

1. **Task 3** (host.json) — 5 minutos, zero risco de regressão
2. **Task 7** (filelock.Timeout) — 15 minutos, melhora resiliência de todas as tasks seguintes
3. **Task 1** (FileLock KB) — 30 minutos, CRITICAL, previne perda de dados
4. **Task 2** (locked_status Approve) — 20 minutos, CRITICAL, depende conceptualmente de Task 1
5. **Task 5** (Poison queue) — 20 minutos, melhora observabilidade
6. **Task 6** (Rate limiter) — 15 minutos, melhora estabilidade LLM
7. **Task 4** (Consolidação) — 40 minutos, maior escopo de mudança

Total estimado: ~2.5 horas de implementação.

---

## Validação Final

Após todas as tasks:

- [ ] `python3 -m pytest tests/ -v` — todos os testes passam
- [ ] `python3 -m pytest tests/ --cov=src --cov-report=term-missing` — coverage não diminuiu
- [ ] Verificar que `host.json` é JSON válido
- [ ] Verificar que nenhum import circular foi introduzido: `python3 -c "from blueprints.worker_bp import worker_bp"`
