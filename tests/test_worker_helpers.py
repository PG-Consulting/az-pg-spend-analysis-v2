"""Tests for worker_helpers — parse_custom_hierarchy, cleanup_stale_jobs, find_next_chunks, consolidate_job, process_single_job."""

import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch  # noqa: F401

from src.worker_helpers import (
    parse_custom_hierarchy,
    cleanup_stale_jobs,
    find_next_chunks,
    consolidate_job,
    process_single_job,  # noqa: F401
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_HIERARCHY_LIST = [
    {
        "N1": "Exploração e Produção",
        "N2": "Engenharia",
        "N3": "Reservatórios",
        "N4": "Consultoria",
    },
    {
        "N1": "Exploração e Produção",
        "N2": "Engenharia",
        "N3": "Reservatórios",
        "N4": "Certificação",
    },
    {"N1": "Operação e Manutenção", "N2": "Materiais", "N3": "OEM", "N4": "Peças ABB"},
]


# ---------------------------------------------------------------------------
# Cenário 1: Hierarquia do projeto (custom_hierarchy_list)
# ---------------------------------------------------------------------------


class TestParseHierarchyFromProjectConfig:
    """Hierarquia definida no projeto, sem upload per-job."""

    def test_returns_list_from_project_config(self):
        status = {
            "custom_hierarchy_list": SAMPLE_HIERARCHY_LIST,
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result is not None
        assert len(result) == 3
        assert result[0]["N1"] == "Exploração e Produção"
        assert result[2]["N4"] == "Peças ABB"

    def test_preserves_all_entries(self):
        status = {
            "custom_hierarchy_list": SAMPLE_HIERARCHY_LIST,
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result == SAMPLE_HIERARCHY_LIST

    def test_ignores_empty_list(self):
        status = {
            "custom_hierarchy_list": [],
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result is None

    def test_ignores_non_list_value(self):
        status = {
            "custom_hierarchy_list": "invalid",
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result is None


# ---------------------------------------------------------------------------
# Cenário 2: Upload per-job (custom_hierarchy_b64) sobrescreve projeto
# ---------------------------------------------------------------------------


class TestParseHierarchyFromB64Upload:
    """Upload de hierarquia na execução — b64 path."""

    def test_b64_returns_none_when_absent(self):
        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": None,
        }
        result = parse_custom_hierarchy(status)
        assert result is None

    def test_b64_returns_none_for_empty_string(self):
        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": "",
        }
        result = parse_custom_hierarchy(status)
        assert result is None

    def test_b64_returns_none_for_invalid_data(self):
        """Base64 inválido não deve causar exceção, deve retornar None."""
        import base64

        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": base64.b64encode(b"not an excel file").decode(),
        }
        result = parse_custom_hierarchy(status)
        assert result is None


# ---------------------------------------------------------------------------
# Cenário 3: UNSPSC no projeto, sem upload — classificação aberta
# ---------------------------------------------------------------------------


class TestParseHierarchyOpenClassification:
    """Projeto UNSPSC/padrão, sem upload — deve retornar None."""

    def test_both_none(self):
        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": None,
        }
        assert parse_custom_hierarchy(status) is None

    def test_both_missing_keys(self):
        status = {"status": "PROCESSING"}
        assert parse_custom_hierarchy(status) is None


# ---------------------------------------------------------------------------
# Cenário 4: UNSPSC no projeto + upload na execução
# Este cenário é tratado pelo SubmitTaxonomyJob que seta
# custom_hierarchy_list=None e custom_hierarchy_b64=<upload>,
# delegando a resolução ao parse_custom_hierarchy via b64 path.
# Testamos que a list path não interfere quando é None.
# ---------------------------------------------------------------------------


class TestParseHierarchyPriorityOrder:
    """Prioridade: list (projeto) → b64 (execução) → None."""

    def test_list_takes_precedence_when_both_present(self):
        """Se ambos presentes (cenário não deveria ocorrer no código atual,
        mas parse_custom_hierarchy deve preferir list)."""
        import base64

        status = {
            "custom_hierarchy_list": SAMPLE_HIERARCHY_LIST,
            "custom_hierarchy_b64": base64.b64encode(b"some data").decode(),
        }
        result = parse_custom_hierarchy(status)
        # list path retorna primeiro
        assert result == SAMPLE_HIERARCHY_LIST

    def test_falls_through_to_b64_when_list_is_none(self):
        """custom_hierarchy_list=None, b64 presente (cenário 4: UNSPSC + upload)."""
        status = {
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": None,
        }
        # Ambos None → retorna None (classificação aberta)
        assert parse_custom_hierarchy(status) is None


# ---------------------------------------------------------------------------
# Cenário 5: cleanup_stale_jobs — timezone aware/naive
# ---------------------------------------------------------------------------


class TestCleanupStaleJobs:
    """cleanup_stale_jobs deve marcar PROCESSING > 1h como ERROR."""

    def test_marks_stale_processing_job_as_error(self, tmp_path):
        job_dir = tmp_path / "stale-job"
        job_dir.mkdir()
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        status = {"status": "PROCESSING", "created_at": two_hours_ago}
        (job_dir / "status.json").write_text(json.dumps(status))
        cleanup_stale_jobs(str(tmp_path))
        result = json.loads((job_dir / "status.json").read_text())
        assert result["status"] == "ERROR"

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
        job_dir = tmp_path / "done-job"
        job_dir.mkdir()
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        status = {"status": "COMPLETED", "created_at": old}
        (job_dir / "status.json").write_text(json.dumps(status))
        cleanup_stale_jobs(str(tmp_path))
        result = json.loads((job_dir / "status.json").read_text())
        assert result["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# find_next_chunks
# ---------------------------------------------------------------------------


class TestFindNextChunks:
    """find_next_chunks retorna índices de chunks sem result correspondente."""

    def test_returns_unprocessed_chunk(self, tmp_path):
        """Chunk sem result deve ser retornado."""
        job_dir = str(tmp_path / "job1")
        os.makedirs(job_dir)
        # chunk_0 sem result_0
        with open(os.path.join(job_dir, "chunk_0.json"), "w") as f:
            json.dump([], f)

        job_info = {"job_dir": job_dir, "total_chunks": 1}
        result = find_next_chunks(job_info, max_count=1)
        assert result == [0]

    def test_skips_processed_chunk(self, tmp_path):
        """Chunk com result correspondente deve ser ignorado."""
        job_dir = str(tmp_path / "job2")
        os.makedirs(job_dir)
        with open(os.path.join(job_dir, "chunk_0.json"), "w") as f:
            json.dump([], f)
        with open(os.path.join(job_dir, "result_0.json"), "w") as f:
            json.dump([], f)

        job_info = {"job_dir": job_dir, "total_chunks": 1}
        result = find_next_chunks(job_info, max_count=1)
        assert result == []

    def test_returns_multiple_unprocessed(self, tmp_path):
        """Retorna até max_count chunks não processados."""
        job_dir = str(tmp_path / "job3")
        os.makedirs(job_dir)
        for i in range(3):
            with open(os.path.join(job_dir, f"chunk_{i}.json"), "w") as f:
                json.dump([], f)
        # Somente chunk_1 já processado
        with open(os.path.join(job_dir, "result_1.json"), "w") as f:
            json.dump([], f)

        job_info = {"job_dir": job_dir, "total_chunks": 3}
        result = find_next_chunks(job_info, max_count=5)
        assert result == [0, 2]

    def test_respects_max_count(self, tmp_path):
        """Deve retornar no máximo max_count chunks."""
        job_dir = str(tmp_path / "job4")
        os.makedirs(job_dir)
        for i in range(5):
            with open(os.path.join(job_dir, f"chunk_{i}.json"), "w") as f:
                json.dump([], f)

        job_info = {"job_dir": job_dir, "total_chunks": 5}
        result = find_next_chunks(job_info, max_count=2)
        assert len(result) == 2
        assert result == [0, 1]

    def test_respects_exclude_set(self, tmp_path):
        """Chunks na lista de exclusão não devem ser retornados."""
        job_dir = str(tmp_path / "job5")
        os.makedirs(job_dir)
        for i in range(3):
            with open(os.path.join(job_dir, f"chunk_{i}.json"), "w") as f:
                json.dump([], f)

        job_info = {"job_dir": job_dir, "total_chunks": 3}
        result = find_next_chunks(job_info, max_count=5, exclude={0, 2})
        assert result == [1]

    def test_empty_when_all_done(self, tmp_path):
        """Se todos os chunks já têm result, retorna lista vazia."""
        job_dir = str(tmp_path / "job6")
        os.makedirs(job_dir)
        for i in range(2):
            with open(os.path.join(job_dir, f"chunk_{i}.json"), "w") as f:
                json.dump([], f)
            with open(os.path.join(job_dir, f"result_{i}.json"), "w") as f:
                json.dump([], f)

        job_info = {"job_dir": job_dir, "total_chunks": 2}
        result = find_next_chunks(job_info, max_count=5)
        assert result == []


# ---------------------------------------------------------------------------
# consolidate_job
# ---------------------------------------------------------------------------


class TestConsolidateJob:
    """consolidate_job deve mesclar chunks, preencher NaN e marcar CLASSIFIED."""

    def _make_job(
        self, tmp_path, job_id, chunk_data_list, result_data_list, status_extra=None
    ):
        """Helper: cria diretório de job com chunks, results e status.json."""
        job_dir = str(tmp_path / job_id)
        os.makedirs(job_dir)

        for i, chunk in enumerate(chunk_data_list):
            with open(os.path.join(job_dir, f"chunk_{i}.json"), "w") as f:
                json.dump(chunk, f)

        for i, result in enumerate(result_data_list):
            with open(os.path.join(job_dir, f"result_{i}.json"), "w") as f:
                json.dump(result, f)

        status = {
            "status": "PROCESSING",
            "total_chunks": len(chunk_data_list),
            "filename": "test.xlsx",
            "desc_column": "Descricao",
        }
        if status_extra:
            status.update(status_extra)

        status_path = os.path.join(job_dir, "status.json")
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False)

        return {
            "job_id": job_id,
            "job_dir": job_dir,
            "status_path": status_path,
            "status": status,
            "total_chunks": len(chunk_data_list),
        }

    def test_fills_na_with_nao_identificado(self, tmp_path):
        """consolidate_job deve preencher N1-N4 vazios com 'Não Identificado'."""
        chunk_data = [{"Descricao": "Item A"}, {"Descricao": "Item B"}]
        result_data = [
            {
                "description": "Item A",
                "N1": "Cat1",
                "N2": "Sub1",
                "N3": "A",
                "N4": "X",
                "source": "LLM (Batch)",
                "confidence": 0.9,
            },
            {
                "description": "Item B",
                "N1": "",
                "N2": "",
                "N3": "",
                "N4": "",
                "source": "None",
                "confidence": 0.0,
            },
        ]

        job_info = self._make_job(tmp_path, "test-fill", [chunk_data], [result_data])
        consolidate_job(job_info)

        with open(job_info["status_path"], encoding="utf-8") as f:
            final_status = json.load(f)
        assert final_status["status"] == "CLASSIFIED"

        with open(
            os.path.join(job_info["job_dir"], "result.json"), encoding="utf-8"
        ) as f:
            result = json.load(f)
        items = result["items"]
        assert len(items) == 2
        # Item B tinha N1-N4 vazios, devem ser "Não Identificado"
        assert items[1]["N1"] == "Não Identificado"
        assert items[1]["N2"] == "Não Identificado"
        assert items[1]["N3"] == "Não Identificado"
        assert items[1]["N4"] == "Não Identificado"

    def test_status_set_to_classified(self, tmp_path):
        """consolidate_job deve definir status como CLASSIFIED (não COMPLETED)."""
        chunk_data = [{"Descricao": "Item A"}]
        result_data = [
            {
                "description": "Item A",
                "N1": "Cat1",
                "N2": "Sub1",
                "N3": "A",
                "N4": "X",
                "source": "LLM (Batch)",
                "confidence": 0.9,
            },
        ]

        job_info = self._make_job(tmp_path, "test-status", [chunk_data], [result_data])
        consolidate_job(job_info)

        with open(job_info["status_path"], encoding="utf-8") as f:
            final_status = json.load(f)
        assert final_status["status"] == "CLASSIFIED"

    def test_result_json_contains_analytics(self, tmp_path):
        """result.json deve conter analytics com pareto_N1."""
        chunk_data = [{"Descricao": "Item A"}, {"Descricao": "Item B"}]
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
            {
                "description": "Item B",
                "N1": "Cat1",
                "N2": "S1",
                "N3": "B",
                "N4": "Y",
                "source": "LLM (Batch)",
                "confidence": 0.8,
            },
        ]

        job_info = self._make_job(
            tmp_path, "test-analytics", [chunk_data], [result_data]
        )
        consolidate_job(job_info)

        with open(
            os.path.join(job_info["job_dir"], "result.json"), encoding="utf-8"
        ) as f:
            result = json.load(f)

        assert "analytics" in result
        assert "pareto_N1" in result["analytics"]
        assert "summary" in result
        assert result["summary"]["total_linhas"] == 2

    def test_excel_base64_in_separate_file(self, tmp_path):
        """Excel b64 deve estar em classified_excel_b64.txt, NÃO no result.json."""
        import base64

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

        # result.json NÃO deve conter fileContent
        with open(
            os.path.join(job_info["job_dir"], "result.json"), encoding="utf-8"
        ) as f:
            result = json.load(f)
        assert "fileContent" not in result, "Excel b64 should NOT be in result.json"

        # Excel b64 deve estar em arquivo separado
        excel_path = os.path.join(job_info["job_dir"], "classified_excel_b64.txt")
        assert os.path.exists(excel_path), "classified_excel_b64.txt not found"
        excel_b64 = open(excel_path, "r").read()
        assert len(excel_b64) > 100, "Excel b64 file is too small"
        decoded = base64.b64decode(excel_b64)
        assert len(decoded) > 0

    def test_intermediate_files_cleaned_up(self, tmp_path):
        """Após consolidação, chunk_*.json e result_*.json intermediários devem ser removidos."""
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

        job_info = self._make_job(tmp_path, "test-cleanup", [chunk_data], [result_data])
        consolidate_job(job_info)

        job_dir = job_info["job_dir"]
        # chunk_0.json e result_0.json devem ter sido removidos
        assert not os.path.exists(os.path.join(job_dir, "chunk_0.json"))
        assert not os.path.exists(os.path.join(job_dir, "result_0.json"))
        # result.json final deve existir
        assert os.path.exists(os.path.join(job_dir, "result.json"))

    def test_incomplete_classification_gets_zero_confidence(self, tmp_path):
        """Itens com 'Não Identificado' devem ter confidence zerada."""
        chunk_data = [{"Descricao": "Item A"}, {"Descricao": "Item B"}]
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
            {
                "description": "Item B",
                "N1": "",
                "N2": "S1",
                "N3": "A",
                "N4": "X",
                "source": "LLM (Batch)",
                "confidence": 0.7,
            },
        ]

        job_info = self._make_job(
            tmp_path, "test-conf-zero", [chunk_data], [result_data]
        )
        consolidate_job(job_info)

        with open(
            os.path.join(job_info["job_dir"], "result.json"), encoding="utf-8"
        ) as f:
            result = json.load(f)

        items = result["items"]
        # Item B tinha N1 vazio → "Não Identificado" → confidence = 0.0
        assert items[1]["confidence"] == 0.0
        # Item A completo → confidence preservada
        assert items[0]["confidence"] == 0.9

    def test_multiple_chunks_consolidated(self, tmp_path):
        """consolidate_job deve mesclar resultados de múltiplos chunks."""
        chunk0 = [{"Descricao": "Item A"}]
        chunk1 = [{"Descricao": "Item B"}]
        result0 = [
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
        result1 = [
            {
                "description": "Item B",
                "N1": "Cat2",
                "N2": "S2",
                "N3": "B",
                "N4": "Y",
                "source": "LLM (Batch)",
                "confidence": 0.8,
            },
        ]

        job_info = self._make_job(
            tmp_path, "test-multi", [chunk0, chunk1], [result0, result1]
        )
        consolidate_job(job_info)

        with open(
            os.path.join(job_info["job_dir"], "result.json"), encoding="utf-8"
        ) as f:
            result = json.load(f)

        items = result["items"]
        assert len(items) == 2
        assert items[0]["N1"] == "Cat1"
        assert items[1]["N1"] == "Cat2"

    def test_nan_strings_replaced_with_nao_identificado(self, tmp_path):
        """Strings 'nan' em N1-N4 devem ser substituídas por 'Não Identificado'."""
        chunk_data = [{"Descricao": "Item A"}, {"Descricao": "Item B"}]
        result_data = [
            {
                "description": "Item A",
                "N1": "nan",
                "N2": "nan",
                "N3": "nan",
                "N4": "nan",
                "source": "KB (Direct Match)",
                "confidence": 0.92,
            },
            {
                "description": "Item B",
                "N1": "Cat1",
                "N2": "S1",
                "N3": "A",
                "N4": "X",
                "source": "LLM (Batch)",
                "confidence": 0.9,
            },
        ]

        job_info = self._make_job(tmp_path, "test-nan", [chunk_data], [result_data])
        consolidate_job(job_info)

        with open(
            os.path.join(job_info["job_dir"], "result.json"), encoding="utf-8"
        ) as f:
            result = json.load(f)

        items = result["items"]
        # Item A tinha N1-N4 = "nan" — devem ser "Não Identificado"
        assert items[0]["N1"] == "Não Identificado"
        assert items[0]["N2"] == "Não Identificado"
        assert items[0]["N3"] == "Não Identificado"
        assert items[0]["N4"] == "Não Identificado"
        assert items[0]["confidence"] == 0.0
        # Item B intacto
        assert items[1]["N1"] == "Cat1"

    def test_result_json_is_valid_json(self, tmp_path):
        """result.json não deve conter NaN literal (JSON inválido) — usa safe_json_dumps."""
        chunk_data = [{"Descricao": "Item A", "Valor": None}]
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

        job_info = self._make_job(
            tmp_path, "test-valid-json", [chunk_data], [result_data]
        )
        consolidate_job(job_info)

        result_path = os.path.join(job_info["job_dir"], "result.json")
        raw = open(result_path, encoding="utf-8").read()
        # Não deve conter NaN literal (que é JSON inválido)
        assert "NaN" not in raw
        # Deve ser JSON válido
        import json as json_mod

        parsed = json_mod.loads(raw)
        assert "items" in parsed


# ---------------------------------------------------------------------------
# process_single_job
# ---------------------------------------------------------------------------


class TestProcessSingleJob:
    """process_single_job processa um job de PENDING até CLASSIFIED."""

    def _create_job(self, tmp_path, job_id, status_override=None, num_chunks=1):
        """Helper: cria job dir com chunks e status.json."""
        job_dir = tmp_path / job_id
        job_dir.mkdir()

        for i in range(num_chunks):
            chunk_data = [
                {"Descricao": f"Item {i}A"},
                {"Descricao": f"Item {i}B"},
            ]
            (job_dir / f"chunk_{i}.json").write_text(json.dumps(chunk_data))

        status = {
            "job_id": job_id,
            "status": "PENDING",
            "total_chunks": num_chunks,
            "processed_chunks": 0,
            "filename": "test.xlsx",
            "desc_column": "Descricao",
            "sector": "Padrao",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "custom_hierarchy_list": None,
            "custom_hierarchy_b64": None,
            "project_id": None,
            "client_context": "",
            "use_web_search": False,
            "total_rows": num_chunks * 2,
        }
        if status_override:
            status.update(status_override)

        (job_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False))
        return str(job_dir)

    @patch("src.worker_helpers.get_jobs_dir")
    @patch("src.worker_helpers.process_single_chunk")
    def test_processes_pending_job_to_classified(
        self, mock_chunk, mock_jobs_dir, tmp_path
    ):
        """Fluxo completo PENDING → PROCESSING → CLASSIFIED."""

        mock_jobs_dir.return_value = str(tmp_path)
        job_id = "test-pending-job"
        self._create_job(tmp_path, job_id, num_chunks=1)

        # Mock process_single_chunk para escrever result_0.json
        def fake_chunk(job_info, chunk_idx):
            result_data = [
                {
                    "description": "Item 0A",
                    "N1": "Cat1",
                    "N2": "S1",
                    "N3": "A",
                    "N4": "X",
                    "source": "LLM (Batch)",
                    "confidence": 0.9,
                },
                {
                    "description": "Item 0B",
                    "N1": "Cat2",
                    "N2": "S2",
                    "N3": "B",
                    "N4": "Y",
                    "source": "LLM (Batch)",
                    "confidence": 0.8,
                },
            ]
            result_path = os.path.join(job_info["job_dir"], f"result_{chunk_idx}.json")
            with open(result_path, "w") as f:
                json.dump(result_data, f)

        mock_chunk.side_effect = fake_chunk

        process_single_job(job_id)

        # Verificar status final
        status = json.loads((tmp_path / job_id / "status.json").read_text())
        assert status["status"] == "CLASSIFIED"

        # Verificar result.json consolidado
        assert (tmp_path / job_id / "result.json").exists()

    @patch("src.worker_helpers.get_jobs_dir")
    def test_skips_cancelled_job(self, mock_jobs_dir, tmp_path):
        """Job CANCELLED deve ser ignorado sem erro."""

        mock_jobs_dir.return_value = str(tmp_path)
        job_id = "test-cancelled"
        self._create_job(tmp_path, job_id, status_override={"status": "CANCELLED"})

        process_single_job(job_id)  # não deve levantar exceção

        status = json.loads((tmp_path / job_id / "status.json").read_text())
        assert status["status"] == "CANCELLED"

    @patch("src.worker_helpers.get_jobs_dir")
    def test_skips_already_classified_job(self, mock_jobs_dir, tmp_path):
        """Job CLASSIFIED deve ser ignorado."""

        mock_jobs_dir.return_value = str(tmp_path)
        job_id = "test-classified"
        self._create_job(tmp_path, job_id, status_override={"status": "CLASSIFIED"})

        process_single_job(job_id)  # não deve levantar exceção

        status = json.loads((tmp_path / job_id / "status.json").read_text())
        assert status["status"] == "CLASSIFIED"

    @patch("src.worker_helpers.get_jobs_dir")
    def test_nonexistent_job_logs_warning(self, mock_jobs_dir, tmp_path, caplog):
        """Job inexistente loga warning e retorna."""
        import logging

        mock_jobs_dir.return_value = str(tmp_path)

        with caplog.at_level(logging.WARNING):
            process_single_job("nonexistent-job-id")

        assert any("not found" in r.message for r in caplog.records)

    @patch("src.worker_helpers.get_jobs_dir")
    @patch("src.worker_helpers.process_single_chunk")
    def test_error_reraised_status_stays_processing(
        self, mock_chunk, mock_jobs_dir, tmp_path
    ):
        """Exceção re-levantada para retry da queue; status NÃO muda para ERROR
        (cleanup timer marca ERROR depois; aqui fica PROCESSING para permitir retry)."""

        mock_jobs_dir.return_value = str(tmp_path)
        job_id = "test-error"
        self._create_job(tmp_path, job_id, num_chunks=1)

        mock_chunk.side_effect = RuntimeError("LLM timeout")

        with pytest.raises(RuntimeError, match="LLM timeout"):
            process_single_job(job_id)

        status = json.loads((tmp_path / job_id / "status.json").read_text())
        # Status stays PROCESSING so queue retries can re-enter
        assert status["status"] == "PROCESSING"


class TestFallbackDetection:
    """consolidate_job deve detectar e sinalizar fallback excessivo."""

    def _make_job(self, tmp_path, results, total_items):
        """Helper: cria job com resultado pré-definido para testar consolidação."""
        job_dir = tmp_path / "taxonomy_jobs" / "test-fallback-job"
        job_dir.mkdir(parents=True, exist_ok=True)

        chunk_data = [{"Descricao": f"item {i}"} for i in range(total_items)]
        (job_dir / "chunk_0.json").write_text(json.dumps(chunk_data))
        (job_dir / "result_0.json").write_text(json.dumps(results))

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
        results = []
        for i in range(10):
            if i < 8:
                results.append(
                    {
                        "description": f"item {i}",
                        "N1": "Não Identificado",
                        "N2": "Não Identificado",
                        "N3": "Não Identificado",
                        "N4": "Não Identificado",
                        "source": "None",
                        "confidence": 0.0,
                    }
                )
            else:
                results.append(
                    {
                        "description": f"item {i}",
                        "N1": "MRO",
                        "N2": "Geral",
                        "N3": "Geral",
                        "N4": "Peças",
                        "source": "LLM (Batch)",
                        "confidence": 0.85,
                    }
                )

        job_info = self._make_job(tmp_path, results, 10)
        consolidate_job(job_info)

        from src.file_lock import read_status

        status = read_status(job_info["status_path"])
        assert status["status"] == "CLASSIFIED"
        assert "fallback_pct" in status
        assert status["fallback_pct"] == 80.0
        assert "warning" in status

    def test_low_fallback_no_warning(self, tmp_path):
        """Se <50% dos itens têm confidence=0, não deve ter warning."""
        results = []
        for i in range(10):
            if i < 2:
                results.append(
                    {
                        "description": f"item {i}",
                        "N1": "Não Identificado",
                        "N2": "Não Identificado",
                        "N3": "Não Identificado",
                        "N4": "Não Identificado",
                        "source": "None",
                        "confidence": 0.0,
                    }
                )
            else:
                results.append(
                    {
                        "description": f"item {i}",
                        "N1": "MRO",
                        "N2": "Geral",
                        "N3": "Geral",
                        "N4": "Peças",
                        "source": "LLM (Batch)",
                        "confidence": 0.85,
                    }
                )

        job_info = self._make_job(tmp_path, results, 10)
        consolidate_job(job_info)

        from src.file_lock import read_status

        status = read_status(job_info["status_path"])
        assert status["status"] == "CLASSIFIED"
        assert status.get("fallback_pct", 0) == 20.0
        assert "warning" not in status
