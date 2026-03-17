# Production Hardening Phase 2 — Plano de Implementação

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 5 correções estruturais de resiliência — sem alterar funcionalidades existentes.

**Architecture:** Todas as mudanças são internas (reordenação de operações, retorno de status, validação de input, limpeza de disco, health probe). Nenhum endpoint novo. Nenhuma mudança de API visível ao frontend. Os testes existentes (314 backend) devem continuar passando.

**Tech Stack:** Python 3.9+ (Azure Functions, filelock, requests), host.json

**Princípio:** Tasks são independentes. Podem ser implementadas em qualquer ordem ou em paralelo (exceto Tasks 1 e 2 que tocam arquivos diferentes).

---

## Mapa de Arquivos

| Task | Arquivo | Ação |
|------|---------|------|
| 1 | `blueprints/review_bp.py:177-218` | Modificar (reordenar KB → status) |
| 1 | `tests/test_review_bp.py` | Adicionar testes |
| 2 | `src/queue_helpers.py:12-43` | Modificar (retornar bool) |
| 2 | `blueprints/classification_bp.py:237-244` | Modificar (warning no response) |
| 2 | `tests/test_queue_helpers.py` | Adicionar testes |
| 3 | `blueprints/health_bp.py` | Modificar (probe Grok) |
| 3 | `tests/test_health.py` | Adicionar testes |
| 4 | `blueprints/worker_bp.py:48-84` | Modificar (retenção de jobs) |
| 4 | `tests/test_worker_bp.py` | Adicionar testes |
| 5 | `blueprints/classification_bp.py:136-160` | Modificar (limite de linhas) |
| 5 | `tests/test_classification_bp.py` | Adicionar testes |

---

## Task 1: Reordenar ApproveClassifications — KB update após status check

**Problema:** Hoje `kb.add_entries()` acontece na linha 213, ANTES da verificação atômica de status na linha 283. Se o job foi cancelado entre essas duas operações, a KB recebe entries órfãs.

**Correção:** Mover o bloco de KB update para DEPOIS do `locked_status()`. Se o status check falhar, a KB não é tocada.

**Files:**
- Modify: `blueprints/review_bp.py:177-304`
- Test: `tests/test_review_bp.py`

- [ ] **Step 1: Escrever teste para verificar que KB não é atualizada se status inválido**

Adicionar ao final de `tests/test_review_bp.py`:

```python
class TestApproveKBOrdering:
    """KB só deve ser atualizada APÓS verificação de status."""

    def test_kb_not_updated_when_status_is_cancelled(self, tmp_path):
        """Se job está CANCELLED, KB não deve receber entries."""
        # Setup: job com status CANCELLED
        job_dir = tmp_path / "jobs" / "test-cancelled"
        job_dir.mkdir(parents=True)
        status = {"status": "CANCELLED", "filename": "test.xlsx"}
        (job_dir / "status.json").write_text(json.dumps(status))

        # Setup: project com KB vazia
        project_dir = tmp_path / "projects" / "test-proj"
        project_dir.mkdir(parents=True)
        (project_dir / "knowledge_base.json").write_text("[]")
        (project_dir / "project_config.json").write_text(json.dumps({
            "project_id": "test-proj", "sector": "test"
        }))

        from blueprints.review_bp import approve_classifications_endpoint

        req = MagicMock()
        req.get_json.return_value = {
            "jobId": "test-cancelled",
            "projectId": "test-proj",
            "decisions": [{
                "index": 0,
                "description": "Item teste",
                "decision": "edited",
                "N1": "MRO", "N2": "Geral", "N3": "Geral", "N4": "Peças",
                "confidence": 1.0,
                "source": "consultant_correction",
                "contribute_to_kb": True,
            }],
        }

        with patch("blueprints.review_bp.get_models_dir", return_value=str(tmp_path)), \
             patch("blueprints.review_bp.get_jobs_dir", return_value=str(tmp_path / "jobs")):
            response = approve_classifications_endpoint(req)

        # Deve retornar erro (ConflictError → 409)
        assert response.status_code == 409

        # KB deve continuar vazia
        kb_data = json.loads((project_dir / "knowledge_base.json").read_text())
        assert len(kb_data) == 0
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_review_bp.py::TestApproveKBOrdering -v --tb=short`
Expected: FAIL — KB recebe entries antes do status check

- [ ] **Step 3: Reordenar operações em approve_classifications_endpoint**

Em `blueprints/review_bp.py`, reestruturar a função. O bloco de KB update (linhas 177-218) deve ser movido para DEPOIS do `locked_status` (linha 283).

Substituir linhas 177-324 (todo o corpo após `if not os.path.isdir(job_dir):`) com:

```python
    # 1. Prepare KB entries (compute, don't persist yet)
    kb_entries_to_add = []
    if project_id:
        for d in decisions:
            if d.get("decision") in ("approved", "edited") and (
                d.get("contribute_to_kb", True) or d.get("decision") == "edited"
            ):
                if any(
                    str(d.get(lvl, "")).strip() in INCOMPLETE_VALUES
                    for lvl in ("N1", "N2", "N3", "N4")
                ):
                    continue
                source = (
                    "consultant_correction"
                    if d.get("decision") == "edited"
                    else "llm_approved"
                )
                kb_entries_to_add.append(
                    {
                        "description": d.get("description", ""),
                        "N1": d.get("N1", ""),
                        "N2": d.get("N2", ""),
                        "N3": d.get("N3", ""),
                        "N4": d.get("N4", ""),
                        "source": source,
                        "confidence": d.get("confidence", 0.85)
                        if source == "llm_approved"
                        else 1.0,
                        "instruction_used": d.get("instruction_used"),
                    }
                )

    # 2. Generate approved Excel from decisions
    import pandas as pd
    from src.exceptions import ConflictError

    status_path = os.path.join(job_dir, "status.json")
    status_data = read_status(status_path)
    current_status = status_data.get("status", "")
    if current_status not in ("CLASSIFIED", "APPROVED"):
        raise ConflictError(
            f"Job {job_id} has status '{current_status}' — only CLASSIFIED or APPROVED jobs can be approved"
        )
    id_col = status_data.get("id_column")
    extra_columns = status_data.get("extra_columns", [])
    id_lookup = {}
    extra_lookup = {}
    result_path = os.path.join(job_dir, "result.json")
    if (id_col or extra_columns) and os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as rf:
            result_tmp = json.load(rf)
        for idx, item in enumerate(result_tmp.get("items", [])):
            if id_col:
                id_lookup[idx] = item.get(id_col, "")
            if extra_columns:
                extra_lookup[idx] = {col: item.get(col, "") for col in extra_columns}

    rows = []
    for d in decisions:
        if d.get("decision") != "rejected":
            row = {}
            if id_col:
                row[id_col] = id_lookup.get(d.get("index", -1), "")
            row["Descrição"] = d.get("description", "")
            item_extras = extra_lookup.get(d.get("index", -1), {})
            for col in extra_columns:
                row[col] = item_extras.get(col, "")
            row["N1"] = d.get("N1", "")
            row["N2"] = d.get("N2", "")
            row["N3"] = d.get("N3", "")
            row["N4"] = d.get("N4", "")
            source = (
                "consultant_correction"
                if d.get("decision") == "edited"
                else d.get("source", "")
            )
            row["Fonte"] = friendly_source_label(source)
            rows.append(row)

    rejected_count = sum(1 for d in decisions if d.get("decision") == "rejected")
    approved_count = sum(1 for d in decisions if d.get("decision") == "approved")
    edited_count = sum(1 for d in decisions if d.get("decision") == "edited")

    df_approved = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_approved.to_excel(writer, index=False, sheet_name="Classificados")
    file_bytes = buf.getvalue()
    file_b64 = base64.b64encode(file_bytes).decode("utf-8")

    # 3. Atomic status transition — MUST succeed before KB update
    from src.file_lock import locked_status

    download_filename = None
    with locked_status(status_path) as locked_data:
        if locked_data.get("status") not in ("CLASSIFIED", "APPROVED"):
            raise ConflictError(
                f"Job {job_id} status changed to '{locked_data.get('status')}' during approval"
            )
        locked_data["status"] = "COMPLETED"
        locked_data["review_completed_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        locked_data["review_summary"] = {
            "total": len(decisions),
            "approved": approved_count,
            "edited": edited_count,
            "rejected": rejected_count,
            "kb_added": 0,  # updated below after KB persist
        }
        original_filename = locked_data.get("filename", "upload.xlsx")
        base_name = os.path.splitext(original_filename)[0]
        download_filename = f"{base_name}_classificado.xlsx"
        locked_data["approved_download_filename"] = download_filename

    # 4. Persist KB entries AFTER status is COMPLETED (safe — no orphans)
    kb_added = 0
    if project_id and kb_entries_to_add:
        try:
            kb = KnowledgeBase(project_id, models_dir)
            kb_added = kb.add_entries(kb_entries_to_add)
            if kb_added > 0:
                kb.create_version_snapshot()
        except Exception as e:
            logger.warning(f"KB update failed: {e}")

    # Update kb_added in status (best-effort, not critical)
    if kb_added > 0:
        try:
            from src.file_lock import update_status
            update_status(status_path, {
                "review_summary": {
                    "total": len(decisions),
                    "approved": approved_count,
                    "edited": edited_count,
                    "rejected": rejected_count,
                    "kb_added": kb_added,
                }
            })
        except Exception:
            pass  # non-critical — summary is informational

    # 5. Save Excel b64 to separate file
    approved_path = os.path.join(job_dir, "approved_result_b64.txt")
    with open(approved_path, "w", encoding="utf-8") as af:
        af.write(file_b64)

    return json_response(
        {
            "success": True,
            "kb_added": kb_added,
            "summary": {
                "total": len(decisions),
                "approved": approved_count,
                "edited": edited_count,
                "rejected": rejected_count,
                "kb_added": kb_added,
            },
            "download_filename": download_filename if rows else None,
            "file_content_base64": file_b64 if rows else None,
        }
    )
```

- [ ] **Step 4: Rodar todos os testes de review**

Run: `python3 -m pytest tests/test_review_bp.py -v --tb=short`
Expected: Todos passando

- [ ] **Step 5: Commit**

```bash
git add blueprints/review_bp.py tests/test_review_bp.py
git commit -m "Fix: reordenar ApproveClassifications — KB update após status check atômico"
```

---

## Task 2: enqueue_job() retornar bool + warning no response

**Problema:** `enqueue_job()` engole exceções silenciosamente. O usuário não sabe que o job ficou órfão na queue.

**Files:**
- Modify: `src/queue_helpers.py:12-43`
- Modify: `blueprints/classification_bp.py:237-244`
- Test: `tests/test_queue_helpers.py`

- [ ] **Step 1: Escrever teste para verificar retorno bool**

Adicionar ao final de `tests/test_queue_helpers.py`:

```python
class TestEnqueueJobReturnValue:
    """enqueue_job deve retornar bool indicando sucesso."""

    def test_returns_false_when_no_connection_string(self):
        """Sem AzureWebJobsStorage, deve retornar False."""
        with patch.dict(os.environ, {"AzureWebJobsStorage": ""}):
            enqueue_job = _reload_enqueue()
            result = enqueue_job("test-job-id")
        assert result is False

    def test_returns_true_on_success(self):
        """Com conexão válida e envio ok, deve retornar True."""
        mock_queue_client = MagicMock()
        mock_queue_class = MagicMock()
        mock_queue_class.from_connection_string.return_value = mock_queue_client
        mock_module = MagicMock()
        mock_module.QueueClient = mock_queue_class

        with patch.dict(os.environ, {"AzureWebJobsStorage": "DefaultEndpoints..."}):
            with patch.dict(sys.modules, {"azure.storage.queue": mock_module}):
                enqueue_job = _reload_enqueue()
                result = enqueue_job("test-job-id")
        assert result is True

    def test_returns_false_on_send_error(self):
        """Se send_message falha, deve retornar False."""
        mock_queue_client = MagicMock()
        mock_queue_client.send_message.side_effect = Exception("Connection refused")
        mock_queue_class = MagicMock()
        mock_queue_class.from_connection_string.return_value = mock_queue_client
        mock_module = MagicMock()
        mock_module.QueueClient = mock_queue_class

        with patch.dict(os.environ, {"AzureWebJobsStorage": "DefaultEndpoints..."}):
            with patch.dict(sys.modules, {"azure.storage.queue": mock_module}):
                enqueue_job = _reload_enqueue()
                result = enqueue_job("test-job-id")
        assert result is False
```

Estes testes seguem o mesmo padrão `patch.dict(sys.modules, ...)` + `_reload_enqueue()` que os testes existentes em `TestEnqueueJob`.

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_queue_helpers.py::TestEnqueueJobReturnValue -v --tb=short`
Expected: FAIL — `enqueue_job` retorna None atualmente

- [ ] **Step 3: Modificar enqueue_job para retornar bool**

Em `src/queue_helpers.py`, substituir a função inteira:

```python
def enqueue_job(job_id: str) -> bool:
    """Enqueue a job message to the taxonomy-jobs queue.

    Returns True if enqueued successfully, False on any failure.
    The cleanup timer serves as safety net for failed enqueues.
    """
    try:
        from azure.storage.queue import QueueClient
    except ImportError:
        logger.error(
            "[Queue] azure-storage-queue não instalado. "
            "Instale com: pip install azure-storage-queue"
        )
        return False

    conn_str = os.environ.get("AzureWebJobsStorage", "")
    if not conn_str:
        logger.error(
            "[Queue] AzureWebJobsStorage não configurado — job não enfileirado"
        )
        return False

    try:
        queue_client = QueueClient.from_connection_string(conn_str, QUEUE_NAME)
        try:
            queue_client.create_queue()
        except Exception:
            pass  # queue já existe — ok
        message = json.dumps({"job_id": job_id})
        queue_client.send_message(message)
        logger.info(f"[Queue] Job {job_id} enfileirado com sucesso")
        return True
    except Exception as e:
        logger.error(f"[Queue] Falha ao enfileirar job {job_id}: {e}")
        return False
```

- [ ] **Step 4: Adicionar warning no SubmitTaxonomyJob response**

Em `blueprints/classification_bp.py`, substituir linhas 237-244:

De:
```python
    from src.queue_helpers import enqueue_job

    enqueue_job(session_id)

    return json_response(
        {"jobId": session_id, "status": "PENDING", "total_chunks": num_chunks},
        status_code=202,
    )
```

Para:
```python
    from src.queue_helpers import enqueue_job

    enqueued = enqueue_job(session_id)

    response_data = {
        "jobId": session_id,
        "status": "PENDING",
        "total_chunks": num_chunks,
    }
    if not enqueued:
        response_data["warning"] = (
            "Job criado mas não enfileirado. "
            "Será processado pelo cleanup automático (até 1h)."
        )

    return json_response(response_data, status_code=202)
```

- [ ] **Step 5: Rodar testes**

Run: `python3 -m pytest tests/test_queue_helpers.py tests/test_classification_bp.py -v --tb=short`
Expected: Todos passando

- [ ] **Step 6: Commit**

```bash
git add src/queue_helpers.py blueprints/classification_bp.py tests/test_queue_helpers.py
git commit -m "Fix: enqueue_job retorna bool — SubmitTaxonomyJob inclui warning se falhar"
```

---

## Task 3: Health check com probe Grok

**Problema:** O health check só verifica se `GROK_API_KEY` existe como variável, não se a API responde.

**Files:**
- Modify: `blueprints/health_bp.py`
- Test: `tests/test_health.py`

- [ ] **Step 1: Escrever teste para probe Grok**

Adicionar ao final de `tests/test_health.py`:

```python
class TestGrokProbe:
    """Health check deve testar conectividade com a API Grok."""

    @patch("blueprints.health_bp.os.path.isdir", return_value=True)
    @patch("blueprints.health_bp.os.environ.get")
    @patch("blueprints.health_bp._probe_grok_api", return_value={"reachable": True, "latency_ms": 150})
    def test_healthy_when_grok_reachable(self, mock_probe, mock_env, mock_isdir):
        """Se Grok responde, status deve ser healthy."""
        mock_env.side_effect = lambda key, *args: "fake-key" if key == "GROK_API_KEY" else ""
        from blueprints.health_bp import HealthCheck
        req = _MockHttpRequest()
        response = HealthCheck(req)
        body = json.loads(response.get_body())
        assert body["status"] == "healthy"
        assert body["checks"]["grok_api_reachable"] is True

    @patch("blueprints.health_bp.os.path.isdir", return_value=True)
    @patch("blueprints.health_bp.os.environ.get")
    @patch("blueprints.health_bp._probe_grok_api", return_value={"reachable": False, "latency_ms": 0})
    def test_degraded_when_grok_unreachable(self, mock_probe, mock_env, mock_isdir):
        """Se Grok não responde, status deve ser degraded."""
        mock_env.side_effect = lambda key, *args: "fake-key" if key == "GROK_API_KEY" else ""
        from blueprints.health_bp import HealthCheck
        req = _MockHttpRequest()
        response = HealthCheck(req)
        body = json.loads(response.get_body())
        assert body["status"] == "degraded"
        assert body["checks"]["grok_api_reachable"] is False
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_health.py::TestGrokProbe -v --tb=short`
Expected: FAIL — `_probe_grok_api` não existe

- [ ] **Step 3: Implementar probe Grok com cache**

Substituir `blueprints/health_bp.py` inteiro:

```python
"""Health check endpoint — quick liveness/readiness probe."""
import os
import time
import logging

import azure.functions as func

from src.api_helpers import json_response, handle_errors
from src.utils import get_models_dir

logger = logging.getLogger(__name__)
health_bp = func.Blueprint()

# Cache for Grok probe (avoid calling API on every health check)
_grok_probe_cache = {"result": None, "timestamp": 0}
_PROBE_CACHE_TTL = 300  # 5 minutes


def _probe_grok_api() -> dict:
    """Test Grok API connectivity with a minimal request. Cached for 5 minutes."""
    now = time.time()
    if _grok_probe_cache["result"] and (now - _grok_probe_cache["timestamp"]) < _PROBE_CACHE_TTL:
        return _grok_probe_cache["result"]

    import requests

    api_key = os.environ.get("GROK_API_KEY", "")
    endpoint = os.environ.get("GROK_API_ENDPOINT", "https://api.x.ai/v1")
    model = os.environ.get("GROK_MODEL_NAME", "grok-4-1-fast-reasoning")

    if not api_key:
        result = {"reachable": False, "latency_ms": 0}
        _grok_probe_cache["result"] = result
        _grok_probe_cache["timestamp"] = now
        return result

    try:
        start = time.time()
        response = requests.post(
            f"{endpoint.rstrip('/')}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "temperature": 0,
            },
            timeout=10,
        )
        latency = round((time.time() - start) * 1000)
        reachable = response.status_code == 200
        result = {"reachable": reachable, "latency_ms": latency}
    except Exception:
        result = {"reachable": False, "latency_ms": 0}

    _grok_probe_cache["result"] = result
    _grok_probe_cache["timestamp"] = now
    return result


@health_bp.route(route="health", methods=["GET"])
@handle_errors("HealthCheck")
def HealthCheck(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/health — returns service status and basic checks."""
    models_dir = get_models_dir()

    grok_probe = _probe_grok_api()

    checks = {
        "filesystem": os.path.isdir(models_dir),
        "grok_api_configured": bool(os.environ.get("GROK_API_KEY")),
        "grok_api_reachable": grok_probe["reachable"],
        "grok_api_latency_ms": grok_probe["latency_ms"],
        "models_dir_configured": bool(models_dir),
    }

    if not checks["filesystem"]:
        status = "degraded"
    elif not checks["grok_api_reachable"]:
        status = "degraded"
    else:
        status = "healthy"

    return json_response({
        "status": status,
        "version": "3.0",
        "checks": checks,
    })
```

- [ ] **Step 4: Atualizar testes existentes para mockar _probe_grok_api**

Os 3 testes existentes em `tests/test_health.py` (`test_returns_200_with_expected_fields`, `test_degraded_when_models_dir_missing`, `test_cors_headers`) vão quebrar porque `_probe_grok_api` faz chamada HTTP real. Adicionar `@patch("blueprints.health_bp._probe_grok_api", return_value={"reachable": True, "latency_ms": 50})` como decorator em cada um dos 3 testes existentes.

Também atualizar assertions nos testes existentes para incluir os novos campos `grok_api_reachable` e `grok_api_latency_ms` no response.

- [ ] **Step 5: Rodar todos os testes de health**

Run: `python3 -m pytest tests/test_health.py -v --tb=short`
Expected: Todos passando (existentes + novos)

- [ ] **Step 6: Commit**

```bash
git add blueprints/health_bp.py tests/test_health.py
git commit -m "Fix: health check com probe Grok — detecta API down com cache de 5min"
```

---

## Task 4: Política de retenção de jobs (piggyback no CleanupStaleJobs)

**Problema:** `taxonomy_jobs/` cresce indefinidamente (10-50MB por job). Sem limpeza.

**Correção:** Adicionar limpeza de jobs COMPLETED/ERROR > 30 dias no `CleanupStaleJobs` (timer que já roda a cada hora).

**Files:**
- Modify: `blueprints/worker_bp.py:48-84`
- Test: `tests/test_worker_bp.py`

- [ ] **Step 1: Escrever teste para retenção**

Adicionar imports no topo de `tests/test_worker_bp.py` (o arquivo atualmente só importa de `src.file_lock` e `src.worker_helpers`):

```python
import json
import os
from datetime import datetime, timezone, timedelta
```

Adicionar ao final de `tests/test_worker_bp.py`:

```python
class TestJobRetention:
    """CleanupStaleJobs deve deletar jobs antigos COMPLETED/ERROR."""

    def test_deletes_completed_job_older_than_30_days(self, tmp_path):
        """Job COMPLETED com mais de 30 dias deve ser deletado."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "old-completed"
        job_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        status = {"status": "COMPLETED", "created_at": old_date}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 1
        assert not job_dir.exists()

    def test_keeps_completed_job_within_30_days(self, tmp_path):
        """Job COMPLETED com menos de 30 dias NÃO deve ser deletado."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "recent-completed"
        job_dir.mkdir()
        recent_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        status = {"status": "COMPLETED", "created_at": recent_date}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 0
        assert job_dir.exists()

    def test_keeps_processing_job_even_if_old(self, tmp_path):
        """Job PROCESSING NÃO deve ser deletado pela retenção."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "old-processing"
        job_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        status = {"status": "PROCESSING", "created_at": old_date}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 0
        assert job_dir.exists()

    def test_deletes_error_job_older_than_30_days(self, tmp_path):
        """Job ERROR com mais de 30 dias deve ser deletado."""
        from src.worker_helpers import cleanup_old_jobs

        job_dir = tmp_path / "old-error"
        job_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        status = {"status": "ERROR", "created_at": old_date}
        (job_dir / "status.json").write_text(json.dumps(status))

        deleted = cleanup_old_jobs(str(tmp_path), max_age_days=30)
        assert deleted == 1
        assert not job_dir.exists()
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_worker_bp.py::TestJobRetention -v --tb=short`
Expected: FAIL — `cleanup_old_jobs` não existe

- [ ] **Step 3: Implementar cleanup_old_jobs em worker_helpers.py**

Adicionar ao final de `src/worker_helpers.py`:

```python
def cleanup_old_jobs(jobs_root: str, max_age_days: int = 30) -> int:
    """Delete job directories for COMPLETED/ERROR jobs older than max_age_days.

    Only deletes terminal-state jobs (COMPLETED, ERROR, CANCELLED).
    Returns count of deleted job directories.
    """
    import shutil

    deleted = 0
    _DELETABLE_STATUSES = ("COMPLETED", "ERROR", "CANCELLED")

    for job_id in os.listdir(jobs_root):
        job_dir = os.path.join(jobs_root, job_id)
        status_path = os.path.join(job_dir, "status.json")
        if not os.path.isdir(job_dir) or not os.path.exists(status_path):
            continue
        try:
            status = read_status(status_path)
            if status.get("status") not in _DELETABLE_STATUSES:
                continue
            created_at = status.get("created_at")
            if not created_at:
                continue
            created_dt = datetime.fromisoformat(created_at)
            age_days = (datetime.now(timezone.utc) - created_dt).total_seconds() / 86400
            if age_days > max_age_days:
                shutil.rmtree(job_dir, ignore_errors=True)
                deleted += 1
                logger.info(
                    f"[Retention] Deleted job {job_id} "
                    f"(status={status.get('status')}, age={age_days:.0f} days)"
                )
        except Exception as e:
            logger.error(f"[Retention] Error checking job {job_id}: {e}")

    return deleted
```

- [ ] **Step 4: Chamar cleanup_old_jobs no CleanupStaleJobs**

Em `blueprints/worker_bp.py`, no final da função `CleanupStaleJobs` (após linha 84), adicionar:

```python
    # 3. Delete old terminal jobs (COMPLETED/ERROR/CANCELLED > 30 days)
    from src.worker_helpers import cleanup_old_jobs

    deleted = cleanup_old_jobs(jobs_root, max_age_days=30)
    if deleted > 0:
        logger.info(f"[Cleanup] Deleted {deleted} old job(s)")
```

- [ ] **Step 5: Rodar todos os testes de worker**

Run: `python3 -m pytest tests/test_worker_bp.py tests/test_worker_helpers.py -v --tb=short`
Expected: Todos passando

- [ ] **Step 6: Commit**

```bash
git add src/worker_helpers.py blueprints/worker_bp.py tests/test_worker_bp.py
git commit -m "Fix: política de retenção — deletar jobs terminais > 30 dias (piggyback no cleanup timer)"
```

---

## Task 5: Limite de upload — rejeitar > 100.000 linhas

**Problema:** Uploads muito grandes podem causar OOM na consolidação.

**Files:**
- Modify: `blueprints/classification_bp.py:136-174`
- Test: `tests/test_classification_bp.py`

- [ ] **Step 1: Escrever teste para limite de linhas**

Adicionar ao final de `tests/test_classification_bp.py`:

```python
class TestUploadRowLimit:
    """SubmitTaxonomyJob deve rejeitar uploads com mais de 100.000 linhas."""

    @patch("blueprints.classification_bp.get_models_dir", return_value="/tmp/models")
    @patch("blueprints.classification_bp.get_jobs_dir", return_value="/tmp/jobs")
    def test_rejects_upload_exceeding_row_limit(self, mock_jobs, mock_models):
        """Upload com >100k linhas deve retornar 400."""
        import pandas as pd
        import base64
        import io

        from blueprints.classification_bp import SubmitTaxonomyJob, MAX_UPLOAD_ROWS

        # Criar um DataFrame com MAX_UPLOAD_ROWS + 1 linhas
        # Para performance, simular via mock do pd.read_excel
        mock_df = pd.DataFrame({
            "ID": range(MAX_UPLOAD_ROWS + 1),
            "Descricao": [f"Item {i}" for i in range(MAX_UPLOAD_ROWS + 1)],
        })

        req = MagicMock()
        req.method = "POST"
        req.get_json.return_value = {
            "fileContent": base64.b64encode(b"fake").decode(),
            "projectId": "test-proj",
        }

        with patch("blueprints.classification_bp.pd.read_excel", return_value=mock_df), \
             patch("blueprints.classification_bp.get_project", return_value={"sector": "test", "client_context": ""}), \
             patch("blueprints.classification_bp.resolve_hierarchy", return_value=(None, "padrao")):
            response = SubmitTaxonomyJob(req)

        assert response.status_code == 400
        body = json.loads(response.get_body())
        assert "100" in body.get("error", "") or "limite" in body.get("error", "").lower()
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_classification_bp.py::TestUploadRowLimit -v --tb=short`
Expected: FAIL — `MAX_UPLOAD_ROWS` não existe

- [ ] **Step 3: Adicionar constante e validação**

Em `blueprints/classification_bp.py`, após a constante `CHUNK_SIZE = 500` (linha 30), adicionar:

```python
MAX_UPLOAD_ROWS = 100_000
```

No `SubmitTaxonomyJob`, após o bloco de leitura do arquivo (após linha 155, onde `df` já está carregado), adicionar:

```python
    if len(df) > MAX_UPLOAD_ROWS:
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)
        raise ValidationError(
            f"Arquivo excede o limite de {MAX_UPLOAD_ROWS:,} linhas "
            f"({len(df):,} linhas). Divida o arquivo em partes menores."
        )
```

Colocar ANTES da detecção de colunas (linha 163: `valid_cols = ...`).

- [ ] **Step 4: Rodar todos os testes de classification**

Run: `python3 -m pytest tests/test_classification_bp.py -v --tb=short`
Expected: Todos passando

- [ ] **Step 5: Commit**

```bash
git add blueprints/classification_bp.py tests/test_classification_bp.py
git commit -m "Fix: limite de upload 100k linhas — previne OOM na consolidação"
```

---

## Verificação Final

- [ ] **Rodar todos os testes backend**

Run: `python3 -m pytest tests/ -v --tb=short`
Expected: Todos os 314+ testes passando (novos testes adicionados)

- [ ] **Rodar testes frontend**

Run: `cd frontend && npx jest --verbose`
Expected: 50 testes passando (nenhuma mudança no frontend)
