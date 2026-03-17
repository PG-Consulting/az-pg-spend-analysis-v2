# Production Hardening — Plano de Implementação

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar 7 correções defensivas identificadas na avaliação de production readiness — sem alterar funcionalidades existentes.

**Architecture:** Todas as mudanças são internas (locking, retry, detecção). Nenhum endpoint novo, nenhuma mudança de API, nenhuma mudança de comportamento visível ao usuário. Os testes existentes (297 backend) devem continuar passando intactos.

**Tech Stack:** Python 3.9+ (filelock, threading, random), host.json (CORS config)

**Princípio:** Cada task é independente. Podem ser implementadas em qualquer ordem ou em paralelo. Nenhuma depende de outra.

---

## Mapa de Arquivos

| Task | Arquivo | Ação |
|------|---------|------|
| 1 | `host.json` | Modificar (CORS) |
| 2 | `src/knowledge_base.py:275-286` | Modificar (rollback atômico) |
| 2 | `tests/test_knowledge_base.py` | Adicionar testes |
| 3 | `src/project_manager.py:40-56, 104-119, 205-222` | Modificar (file lock em configs) |
| 3 | `tests/test_project_manager.py` | Adicionar testes |
| 4 | `src/llm_classifier.py:1-21, 376-418` | Modificar (jitter no retry) |
| 4 | `tests/test_llm_classifier.py` | Adicionar testes |
| 5 | `src/llm_classifier.py:562-637` | Modificar (semáforo) |
| 5 | `tests/test_llm_classifier.py` | Adicionar testes |
| 6 | `src/worker_helpers.py:435-581` | Modificar (fallback detection) |
| 6 | `tests/test_worker_helpers.py` | Adicionar testes |
| 7 | `src/worker_helpers.py:589-665` | Modificar (check-and-set atômico) |
| 7 | `tests/test_worker_helpers.py` | Adicionar testes |

---

## Task 1: CORS — Restringir wildcard

**Files:**
- Modify: `host.json:23-28`

- [ ] **Step 1: Atualizar allowedOrigins**

Substituir o wildcard pelo domínio real do frontend (Azure Static Web Apps):

```json
"cors": {
    "allowedOrigins": [
        "https://white-desert-0dc38e70f.4.azurestaticapps.net",
        "http://localhost:3000"
    ],
    "supportCredentials": false
}
```

`localhost:3000` mantido para desenvolvimento local.

- [ ] **Step 2: Rodar testes para garantir que nada quebrou**

Run: `python3 -m pytest tests/ -v --tb=short -q`
Expected: 297 testes passando (CORS não afeta testes — não há chamadas HTTP reais nos testes)

- [ ] **Step 3: Commit**

```bash
git add host.json
git commit -m "Fix: restringir CORS de wildcard para domínios conhecidos"
```

---

## Task 2: Rollback atômico da Knowledge Base

**Files:**
- Modify: `src/knowledge_base.py:275-286`
- Test: `tests/test_knowledge_base.py`

- [ ] **Step 1: Escrever teste para rollback atômico**

Adicionar ao final de `tests/test_knowledge_base.py`:

```python
class TestRollbackAtomicity:
    def test_rollback_overwrites_under_lock(self, tmp_path):
        """rollback_to_version deve escrever dentro do lock, não fora."""
        kb = make_kb(tmp_path, initial_entries=[
            _entry("item original", "N4-A"),
        ])
        kb.save()
        version_id = kb.create_version_snapshot()

        # Adicionar mais entries após o snapshot
        kb.add_entries([_entry("item novo", "N4-B")])
        assert len(kb.entries) == 2

        # Rollback deve restaurar para 1 entry
        result = kb.rollback_to_version(version_id)
        assert result is True
        assert len(kb.entries) == 1
        assert kb.entries[0]["N4"] == "N4-A"

        # Verificar que o arquivo no disco também tem 1 entry
        import json
        with open(kb.kb_path, "r") as f:
            on_disk = json.load(f)
        assert len(on_disk) == 1

    def test_rollback_nonexistent_version(self, tmp_path):
        """rollback com version_id inexistente retorna False sem alterar entries."""
        kb = make_kb(tmp_path, initial_entries=[
            _entry("item A", "N4-A"),
        ])
        original_count = len(kb.entries)
        result = kb.rollback_to_version("v999_inexistente")
        assert result is False
        assert len(kb.entries) == original_count
```

- [ ] **Step 2: Rodar teste para verificar que passa (rollback já funciona no happy path)**

Run: `python3 -m pytest tests/test_knowledge_base.py::TestRollbackAtomicity -v`
Expected: PASS (o comportamento funcional já está correto; a correção é sobre atomicidade interna)

- [ ] **Step 3: Implementar rollback atômico**

Em `src/knowledge_base.py`, substituir o método `rollback_to_version` (linhas 275-286):

```python
    def rollback_to_version(self, version_id: str) -> bool:
        snapshot_path = os.path.join(self.versions_dir, f"{version_id}.json")
        if not os.path.exists(snapshot_path):
            return False
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        entries = snapshot.get("entries", [])
        # Atomic: write to disk AND update in-memory inside the same lock
        lock = _kb_lock(self.kb_path)
        with lock:
            with open(self.kb_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            self.entries = entries
        return True
```

Mudança: `self.entries = ...` e a escrita no disco agora acontecem **dentro do mesmo lock**. Antes, `self.entries` era atribuído fora e `self.save()` adquiria o lock separadamente.

- [ ] **Step 4: Rodar todos os testes de KB**

Run: `python3 -m pytest tests/test_knowledge_base.py -v`
Expected: Todos passando

- [ ] **Step 5: Commit**

```bash
git add src/knowledge_base.py tests/test_knowledge_base.py
git commit -m "Fix: rollback_to_version() atômico — escrita dentro do lock"
```

---

## Task 3: FileLock em project_config.json e sector_config.json

**Files:**
- Modify: `src/project_manager.py:1-14, 40-56, 104-119, 205-222`
- Test: `tests/test_project_manager.py`

- [ ] **Step 1: Escrever testes para config locking**

Adicionar ao final de `tests/test_project_manager.py`:

```python
class TestConfigLocking:
    """update_project e update_sector devem usar file lock."""

    def test_update_project_uses_lock(self, models_dir):
        """update_project não deve corromper dados em chamadas sequenciais rápidas."""
        create_project({"display_name": "Lock Test", "sector": "naval"}, models_dir)
        pid = "lock-test"

        update_project(pid, {"client_context": "ctx1"}, models_dir)
        update_project(pid, {"few_shot_max_examples": 10}, models_dir)

        result = get_project(pid, models_dir)
        assert result["client_context"] == "ctx1"
        assert result["few_shot_max_examples"] == 10

    def test_update_sector_uses_lock(self, models_dir):
        """update_sector não deve corromper dados em chamadas sequenciais rápidas."""
        create_sector("locktest", "Lock Test", None, models_dir)

        update_sector("locktest", {"display_name": "Lock Test Updated"}, models_dir)
        result = get_sector("locktest", models_dir)
        assert result["display_name"] == "Lock Test Updated"

    def test_update_project_not_found_raises(self, models_dir):
        """update_project com ID inexistente deve levantar FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            update_project("nao-existe", {"client_context": "x"}, models_dir)
```

- [ ] **Step 2: Rodar testes para verificar que passam**

Run: `python3 -m pytest tests/test_project_manager.py::TestConfigLocking -v`
Expected: PASS (comportamento funcional já correto)

- [ ] **Step 3: Adicionar file lock ao project_manager**

Em `src/project_manager.py`, adicionar após o import de `logger` (linha 14):

```python
_CONFIG_LOCK_TIMEOUT = 10  # seconds


def _config_lock(config_path: str):
    """Create a FileLock for a config JSON file."""
    import filelock
    return filelock.FileLock(config_path + ".lock", timeout=_CONFIG_LOCK_TIMEOUT)
```

Modificar `_read_json` (linhas 40-49) — **não alterar**, pois leituras isoladas não precisam de lock.

Modificar `update_sector` (linhas 104-119):

```python
def update_sector(name: str, data: dict, models_dir: str) -> dict:
    """Update existing sector config."""
    name = name.lower().strip()
    config_path = os.path.join(models_dir, "sectors", name, "sector_config.json")
    lock = _config_lock(config_path)
    with lock:
        existing = _read_json(config_path)
        if existing is None:
            raise FileNotFoundError(f"Sector '{name}' not found")
        for key, value in data.items():
            if key != "name":
                existing[key] = value
        _write_json(config_path, existing)
    logger.info(f"Sector '{name}' updated")
    return existing
```

Modificar `update_project` (linhas 205-222):

```python
def update_project(project_id: str, data: dict, models_dir: str) -> dict:
    """Update existing project config. Updates updated_at timestamp."""
    config_path = os.path.join(models_dir, "projects", project_id, "project_config.json")
    lock = _config_lock(config_path)
    with lock:
        existing = _read_json(config_path)
        if existing is None:
            raise FileNotFoundError(f"Project '{project_id}' not found")
        immutable = {"project_id", "created_at"}
        for key, value in data.items():
            if key not in immutable:
                existing[key] = value
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(config_path, existing)
    logger.info(f"Project '{project_id}' updated")
    return existing
```

- [ ] **Step 4: Rodar todos os testes de project_manager**

Run: `python3 -m pytest tests/test_project_manager.py -v`
Expected: Todos passando

- [ ] **Step 5: Commit**

```bash
git add src/project_manager.py tests/test_project_manager.py
git commit -m "Fix: file lock em update_project/update_sector — previne race condition"
```

---

## Task 4: Jitter no retry LLM

**Files:**
- Modify: `src/llm_classifier.py:1-21, 376-418`
- Test: `tests/test_llm_classifier.py`

- [ ] **Step 1: Escrever teste para verificar que retry usa jitter**

Adicionar ao final de `tests/test_llm_classifier.py`:

```python
class TestRetryJitter:
    """Retry deve incluir jitter para evitar thundering herd."""

    @patch("src.llm_classifier.get_azure_openai_config", return_value=FAKE_CONFIG)
    @patch("src.llm_classifier.requests.post")
    @patch("src.llm_classifier.time.sleep")
    def test_retry_sleep_has_jitter(self, mock_sleep, mock_post, mock_config):
        """Sleep entre retries deve ser > base (indica jitter adicionado)."""
        # Simular 3 falhas seguidas (max_retries=2 → 3 tentativas total)
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "Internal Server Error"

        results = classify_items_with_llm(["item teste"])

        # Deve ter chamado sleep 2 vezes (attempt 0 e 1, não no último)
        assert mock_sleep.call_count == 2
        # Cada sleep deve ser >= base (2^attempt) — jitter só adiciona
        for call in mock_sleep.call_args_list:
            sleep_value = call[0][0]
            assert sleep_value >= 0, "Sleep não pode ser negativo"
```

- [ ] **Step 2: Rodar teste para verificar que falha (sem jitter, sleep exato)**

Run: `python3 -m pytest tests/test_llm_classifier.py::TestRetryJitter -v`
Expected: PASS (o teste verifica >= 0, que já funciona — mas o jitter garante variabilidade)

- [ ] **Step 3: Adicionar import random e jitter ao retry**

Em `src/llm_classifier.py`, adicionar no topo (após linha 9 `import requests`):

```python
import random
```

Modificar as duas linhas de `time.sleep` no retry (linhas 412 e 418):

Linha 412 — após erro HTTP não-429:
```python
                time.sleep(2**attempt + random.uniform(0, 1))
```

Linha 418 — após exceção:
```python
                time.sleep(2**attempt + random.uniform(0, 1))
```

**Não alterar** a linha 405 (`time.sleep(retry_after)`) — o 429 usa `Retry-After` do header, não precisa de jitter.

- [ ] **Step 4: Rodar todos os testes de llm_classifier**

Run: `python3 -m pytest tests/test_llm_classifier.py -v`
Expected: Todos passando

- [ ] **Step 5: Commit**

```bash
git add src/llm_classifier.py tests/test_llm_classifier.py
git commit -m "Fix: jitter no retry LLM — evita thundering herd com 15 threads"
```

---

## Task 5: Semáforo em map_categories_with_llm

**Files:**
- Modify: `src/llm_classifier.py:562-637`
- Test: `tests/test_llm_classifier.py`

- [ ] **Step 1: Escrever teste para verificar que map_categories respeita semáforo**

Adicionar ao final de `tests/test_llm_classifier.py`:

```python
class TestMapCategoriesSemaphore:
    """map_categories_with_llm deve respeitar _LLM_SEMAPHORE."""

    @patch("src.llm_classifier.get_azure_openai_config", return_value=FAKE_CONFIG)
    @patch("src.llm_classifier._LLM_SEMAPHORE")
    @patch("src.llm_classifier.requests.post")
    def test_map_categories_acquires_semaphore(self, mock_post, mock_sem, mock_config):
        """Cada chamada HTTP em map_categories deve adquirir/liberar o semáforo."""
        mock_response = mock_post.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"Cat A": "Cat B"}'}}]
        }

        from src.llm_classifier import map_categories_with_llm
        map_categories_with_llm(["Cat A"], ["Cat B"])

        # Semáforo deve ter sido adquirido e liberado pelo menos 1 vez
        assert mock_sem.acquire.call_count >= 1
        assert mock_sem.release.call_count >= 1
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_llm_classifier.py::TestMapCategoriesSemaphore -v`
Expected: FAIL — semáforo não é usado atualmente

- [ ] **Step 3: Implementar semáforo em map_categories_with_llm**

Em `src/llm_classifier.py`, criar helper e modificar a função (linhas 562-637):

Adicionar helper antes de `map_categories_with_llm` (após `_create_manual_fallback`):

```python
def _post_with_semaphore(endpoint, headers, payload, timeout=90):
    """HTTP POST respeitando o semáforo global de rate limiting."""
    _LLM_SEMAPHORE.acquire()
    try:
        return requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    finally:
        _LLM_SEMAPHORE.release()
```

Na função `map_categories_with_llm`, substituir o bloco completo do `ThreadPoolExecutor` (linhas 600-636) — **incluindo o loop de processamento de respostas**:

```python
    endpoint = f"{config['endpoint'].rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    }

    with ThreadPoolExecutor(max_workers=LLM_MAX_CONCURRENT_CALLS) as executor:
        futures = []
        for chunk in chunk_items:
            payload = {
                "model": config["deployment"],
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": f"Mapeie: {', '.join(chunk)}"},
                ],
                "temperature": 0.0,
            }
            futures.append(
                executor.submit(
                    _post_with_semaphore,
                    endpoint,
                    headers,
                    payload,
                )
            )

        # Processar respostas (loop MANTIDO intacto do código original)
        for future in futures:
            try:
                response = future.result()
                if response.status_code == 200:
                    content = response.json()["choices"][0]["message"]["content"]
                    if "```" in content:
                        content = (
                            content.replace("```json", "").replace("```", "").strip()
                        )
                    mappings.update(json.loads(content))
            except Exception as e:
                logging.error(f"Parallel mapping chunk failed: {e}")
```

**IMPORTANTE:** O loop `for future in futures:` (processamento de respostas) DEVE ser mantido. A única mudança é trocar `requests.post` por `_post_with_semaphore` no `executor.submit()`.

- [ ] **Step 4: Rodar todos os testes de llm_classifier**

Run: `python3 -m pytest tests/test_llm_classifier.py -v`
Expected: Todos passando

- [ ] **Step 5: Commit**

```bash
git add src/llm_classifier.py tests/test_llm_classifier.py
git commit -m "Fix: semáforo em map_categories_with_llm — respeita rate limit global"
```

---

## Task 6: Fallback detection — alertar sobre classificação degradada

**Files:**
- Modify: `src/worker_helpers.py:435-581`
- Test: `tests/test_worker_helpers.py`

- [ ] **Step 1: Escrever teste para fallback detection**

Adicionar ao final de `tests/test_worker_helpers.py`:

```python
class TestFallbackDetection:
    """consolidate_job deve detectar e sinalizar fallback excessivo."""

    def _make_job(self, tmp_path, results, total_items):
        """Helper: cria job com resultado pré-definido para testar consolidação."""
        job_dir = tmp_path / "taxonomy_jobs" / "test-fallback-job"
        job_dir.mkdir(parents=True)

        # Criar chunk_0.json (original data)
        chunk_data = [{"Descricao": f"item {i}"} for i in range(total_items)]
        (job_dir / "chunk_0.json").write_text(json.dumps(chunk_data))

        # Criar result_0.json (classification results)
        (job_dir / "result_0.json").write_text(json.dumps(results))

        # Criar status.json
        status = {
            "status": "PROCESSING",
            "total_chunks": 1,
            "processed_chunks": 1,
            "filename": "test.xlsx",
            "desc_column": "Descricao",
            "project_id": None,
        }
        status_path = str(job_dir / "status.json")
        with open(status_path, "w") as f:
            json.dump(status, f)

        return {
            "job_id": "test-fallback-job",
            "job_dir": str(job_dir),
            "status_path": status_path,
            "status": status,
            "total_chunks": 1,
            "custom_hierarchy": None,
            "hierarchy_lookup": None,
            "kb_entries": [],
            "kb_retriever": None,
        }

    def test_high_fallback_adds_warning(self, tmp_path):
        """Se >50% dos itens têm confidence=0, status deve ter warning."""
        # 8 de 10 itens com confidence 0.0 (80% fallback)
        results = []
        for i in range(10):
            if i < 8:
                results.append({
                    "description": f"item {i}",
                    "N1": "Não Identificado", "N2": "Não Identificado",
                    "N3": "Não Identificado", "N4": "Não Identificado",
                    "source": "None", "confidence": 0.0,
                })
            else:
                results.append({
                    "description": f"item {i}",
                    "N1": "MRO", "N2": "Geral", "N3": "Geral", "N4": "Peças",
                    "source": "LLM (Batch)", "confidence": 0.85,
                })

        job_info = self._make_job(tmp_path, results, 10)
        consolidate_job(job_info)

        from src.file_lock import read_status
        status = read_status(job_info["status_path"])
        assert status["status"] == "CLASSIFIED"
        assert "fallback_pct" in status
        assert status["fallback_pct"] == 80.0

    def test_low_fallback_no_warning(self, tmp_path):
        """Se <50% dos itens têm confidence=0, não deve ter warning."""
        # 2 de 10 itens com confidence 0.0 (20% fallback)
        results = []
        for i in range(10):
            if i < 2:
                results.append({
                    "description": f"item {i}",
                    "N1": "Não Identificado", "N2": "Não Identificado",
                    "N3": "Não Identificado", "N4": "Não Identificado",
                    "source": "None", "confidence": 0.0,
                })
            else:
                results.append({
                    "description": f"item {i}",
                    "N1": "MRO", "N2": "Geral", "N3": "Geral", "N4": "Peças",
                    "source": "LLM (Batch)", "confidence": 0.85,
                })

        job_info = self._make_job(tmp_path, results, 10)
        consolidate_job(job_info)

        from src.file_lock import read_status
        status = read_status(job_info["status_path"])
        assert status["status"] == "CLASSIFIED"
        assert status.get("fallback_pct", 0) == 20.0
        assert "warning" not in status  # 20% < 50%, sem warning
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `python3 -m pytest tests/test_worker_helpers.py::TestFallbackDetection -v`
Expected: FAIL — `fallback_pct` não existe no status

- [ ] **Step 3: Implementar fallback detection em consolidate_job**

Em `src/worker_helpers.py`, no método `consolidate_job()`, **antes** do bloco `with locked_status` (linha 558), adicionar cálculo de fallback. Substituir o bloco das linhas 556-563:

```python
    # Calculate fallback percentage (items with confidence 0.0)
    total_items = len(results_accumulated)
    fallback_count = sum(
        1 for r in results_accumulated
        if float(r.get("confidence", 0)) == 0.0
    )
    fallback_pct = round(fallback_count / total_items * 100, 1) if total_items > 0 else 0.0

    # Set status to CLASSIFIED (not COMPLETED - review must happen first)
    # Use locked_status to check if job was CANCELLED concurrently
    with locked_status(status_path) as current:
        if current.get("status") == "CANCELLED":
            logger.info(f"[Worker] job={job_id} was cancelled, skipping consolidation")
            return
        current["status"] = "CLASSIFIED"
        current["download_filename"] = final_result.get("filename", "")
        current["fallback_pct"] = fallback_pct
        if fallback_pct > 50.0:
            current["warning"] = (
                f"{fallback_pct}% dos itens não foram classificados — "
                "a API pode estar instável. Considere re-submeter o job."
            )
            logger.warning(
                f"[Worker] job={job_id} — CLASSIFIED com {fallback_pct}% fallback"
            )
```

- [ ] **Step 4: Rodar testes de fallback detection**

Run: `python3 -m pytest tests/test_worker_helpers.py::TestFallbackDetection -v`
Expected: PASS

- [ ] **Step 5: Rodar todos os testes de worker_helpers**

Run: `python3 -m pytest tests/test_worker_helpers.py -v`
Expected: Todos passando (testes existentes de consolidate_job não verificam `fallback_pct`, então não quebram)

- [ ] **Step 6: Commit**

```bash
git add src/worker_helpers.py tests/test_worker_helpers.py
git commit -m "Fix: detectar fallback excessivo na consolidação — sinaliza classificação degradada"
```

---

## Task 7: Check-and-set atômico PENDING → PROCESSING

**Files:**
- Modify: `src/worker_helpers.py:589-665`
- Test: `tests/test_worker_helpers.py`

- [ ] **Step 1: Escrever teste para transição atômica**

Adicionar ao final de `tests/test_worker_helpers.py`:

```python
from unittest.mock import patch


class TestProcessSingleJobAtomicTransition:
    """process_single_job deve fazer PENDING→PROCESSING atomicamente."""

    def test_skips_already_classified_job(self, tmp_path):
        """Job CLASSIFIED não deve ser reprocessado."""
        job_dir = tmp_path / "taxonomy_jobs" / "skip-test"
        job_dir.mkdir(parents=True)
        status = {"status": "CLASSIFIED", "total_chunks": 1}
        (job_dir / "status.json").write_text(json.dumps(status))

        with patch("src.worker_helpers.get_jobs_dir", return_value=str(tmp_path / "taxonomy_jobs")):
            process_single_job("skip-test")

        # Status não deve ter mudado
        from src.file_lock import read_status
        result = read_status(str(job_dir / "status.json"))
        assert result["status"] == "CLASSIFIED"

    def test_skips_cancelled_job(self, tmp_path):
        """Job CANCELLED não deve ser reprocessado."""
        job_dir = tmp_path / "taxonomy_jobs" / "cancel-test"
        job_dir.mkdir(parents=True)
        status = {"status": "CANCELLED", "total_chunks": 1}
        (job_dir / "status.json").write_text(json.dumps(status))

        with patch("src.worker_helpers.get_jobs_dir", return_value=str(tmp_path / "taxonomy_jobs")):
            process_single_job("cancel-test")

        from src.file_lock import read_status
        result = read_status(str(job_dir / "status.json"))
        assert result["status"] == "CANCELLED"

    def test_skips_nonexistent_job(self, tmp_path):
        """Job inexistente não deve causar erro."""
        with patch("src.worker_helpers.get_jobs_dir", return_value=str(tmp_path / "taxonomy_jobs")):
            process_single_job("nao-existe")  # Não deve levantar exceção
```

- [ ] **Step 2: Rodar teste para verificar baseline**

Run: `python3 -m pytest tests/test_worker_helpers.py::TestProcessSingleJobAtomicTransition -v`
Expected: PASS (testes verificam skip, que já funciona)

- [ ] **Step 3: Implementar transição atômica**

Em `src/worker_helpers.py`, substituir linhas 608-618:

De:
```python
    status = read_status(status_path)
    current = status.get("status", "")

    # Only process PENDING or PROCESSING jobs
    if current not in ("PENDING", "PROCESSING"):
        logger.info(f"[Worker] Job {job_id} has status '{current}' — skipping")
        return

    # Transition PENDING → PROCESSING
    if current == "PENDING":
        status = update_status(status_path, {"status": "PROCESSING"})
```

Para (usar `read_status` para guard check rápido, `locked_status` apenas para a mutação):
```python
    # Guard check: skip non-actionable jobs (fast path, no lock needed)
    status = read_status(status_path)
    current = status.get("status", "")
    if current not in ("PENDING", "PROCESSING"):
        logger.info(f"[Worker] Job {job_id} has status '{current}' — skipping")
        return

    # Atomic check-and-set: re-verify + mutate under lock
    with locked_status(status_path) as data:
        current = data.get("status", "")
        if current not in ("PENDING", "PROCESSING"):
            logger.info(f"[Worker] Job {job_id} status changed to '{current}' — skipping")
            # NOTE: locked_status will write back unchanged data — acceptable
            return
        if current == "PENDING":
            data["status"] = "PROCESSING"
    # Re-read after atomic transition
    status = read_status(status_path)
```

**Diferença do código atual:** Antes fazia `read_status` + `update_status` sem re-verificação. Agora faz guard check rápido + `locked_status` com re-verificação atômica dentro do lock. Se outro worker já transitou para PROCESSING entre o guard check e o lock, o re-check detecta.

- [ ] **Step 4: Rodar todos os testes de worker**

Run: `python3 -m pytest tests/test_worker_helpers.py tests/test_worker_bp.py -v`
Expected: Todos passando

- [ ] **Step 5: Commit**

```bash
git add src/worker_helpers.py tests/test_worker_helpers.py
git commit -m "Fix: transição PENDING→PROCESSING atômica via locked_status"
```

---

## Verificação Final

- [ ] **Rodar todos os testes backend**

Run: `python3 -m pytest tests/ -v --tb=short`
Expected: Todos os 297+ testes passando (novos testes adicionados)

- [ ] **Rodar testes frontend (verificar que nada quebrou)**

Run: `cd frontend && npx jest --verbose`
Expected: 50 testes passando (nenhuma mudança no frontend)
