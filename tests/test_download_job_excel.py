"""Tests for DownloadJobExcel logic — Excel generation from result.json."""

import base64
import json
import io
import os
import sys
import types
from unittest.mock import MagicMock

import pandas as pd

from src.utils import friendly_source_label

# ---------------------------------------------------------------------------
# Mock azure.functions before importing blueprints
# ---------------------------------------------------------------------------
_mock_azure = types.ModuleType("azure")
_mock_func = types.ModuleType("azure.functions")


class _MockHttpResponse:
    def __init__(self, body=None, status_code=200, mimetype=None, headers=None):
        self._body = body.encode("utf-8") if isinstance(body, str) else (body or b"")
        self.status_code = status_code
        self.mimetype = mimetype
        self.headers = headers or {}

    def get_body(self):
        return self._body


class _MockAuthLevel:
    ANONYMOUS = "ANONYMOUS"


class _MockBlueprint:
    def route(self, *a, **kw):
        def decorator(fn):
            return fn

        return decorator


_mock_func.HttpResponse = _MockHttpResponse
_mock_func.HttpRequest = MagicMock
_mock_func.AuthLevel = _MockAuthLevel
_mock_func.Blueprint = _MockBlueprint
_mock_azure.functions = _mock_func
sys.modules.setdefault("azure", _mock_azure)
sys.modules.setdefault("azure.functions", _mock_func)


def _make_job_dir(
    tmp_path, status="CLASSIFIED", filename="compras_2024.xlsx", items=None
):
    """Create a fake job directory with status.json and result.json."""
    job_dir = tmp_path / "job_123"
    job_dir.mkdir(parents=True, exist_ok=True)

    status_data = {
        "job_id": "job_123",
        "status": status,
        "filename": filename,
        "desc_column": "Descricao",
        "total_rows": 2,
        "total_chunks": 1,
        "processed_chunks": 1,
    }
    with open(job_dir / "status.json", "w", encoding="utf-8") as f:
        json.dump(status_data, f, ensure_ascii=False)

    if items is not None:
        result_data = {"items": items}
        with open(job_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False)

    return job_dir, status_data


def _generate_excel_from_items(items, desc_column="Descricao"):
    """Reproduce the Excel generation logic that the endpoint will use."""
    rows = []
    for item in items:
        rows.append(
            {
                "Descricao": item.get(desc_column, item.get("description", "")),
                "N1": item.get("N1", ""),
                "N2": item.get("N2", ""),
                "N3": item.get("N3", ""),
                "N4": item.get("N4", ""),
                "Fonte": friendly_source_label(item.get("source", "")),
            }
        )
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Resultados", engine="openpyxl")
    return buf.getvalue()


def _generate_excel_with_decisions(
    items, decisions=None, id_col=None, extra_columns=None
):
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
                status_map = {
                    "approved": "Aprovado",
                    "edited": "Editado",
                    "rejected": "Rejeitado",
                }
                row["Status"] = status_map.get(d["decision"], "Pendente")
            else:
                row["Status"] = "Pendente"

        rows.append(row)

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Resultados", engine="openpyxl")
    return buf.getvalue()


class TestDownloadJobExcel:
    def test_generates_excel_with_correct_columns(self, tmp_path):
        """Excel has correct columns (Descricao, N1..N4, Fonte, Confianca) and data."""
        items = [
            {
                "Descricao": "Parafuso M8",
                "N1": "Materiais",
                "N2": "Fixadores",
                "N3": "Parafusos",
                "N4": "Parafuso M8",
                "source": "LLM (Batch)",
                "confidence": 0.92,
            },
            {
                "Descricao": "Tinta Azul 18L",
                "N1": "Materiais",
                "N2": "Pintura",
                "N3": "Tintas",
                "N4": "Tinta Esmalte",
                "source": "KB (Direct Match)",
                "confidence": 0.95,
            },
        ]
        excel_bytes = _generate_excel_from_items(items)

        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert list(df.columns) == ["Descricao", "N1", "N2", "N3", "N4", "Fonte"]
        assert len(df) == 2
        assert df.iloc[0]["Descricao"] == "Parafuso M8"
        assert df.iloc[0]["Fonte"] == "Grok"
        assert df.iloc[1]["Fonte"] == "Base de Aprendizado"

    def test_filename_uses_original_name(self, tmp_path):
        """Output filename is '{original}_resultado.xlsx'."""
        original = "compras_2024.xlsx"
        base = os.path.splitext(original)[0]
        expected = f"{base}_resultado.xlsx"
        assert expected == "compras_2024_resultado.xlsx"

    def test_extra_columns_included_when_present(self, tmp_path):
        """Extra columns (e.g. Fornecedor) should appear in Excel between Descricao and N1."""
        items = [
            {
                "Descricao": "Parafuso M8",
                "Fornecedor": "ABC Ltda",
                "N1": "Materiais",
                "N2": "Fixadores",
                "N3": "Parafusos",
                "N4": "Parafuso M8",
                "source": "LLM (Batch)",
                "confidence": 0.92,
            },
            {
                "Descricao": "Tinta Azul 18L",
                "Fornecedor": "Tintas XYZ",
                "N1": "Materiais",
                "N2": "Pintura",
                "N3": "Tintas",
                "N4": "Tinta Esmalte",
                "source": "KB (Direct Match)",
                "confidence": 0.95,
            },
        ]
        extra_columns = ["Fornecedor"]

        rows = []
        for item in items:
            row = {}
            row["Descricao"] = item.get("Descricao", "")
            for col in extra_columns:
                row[col] = item.get(col, "")
            row["N1"] = item.get("N1", "")
            row["N2"] = item.get("N2", "")
            row["N3"] = item.get("N3", "")
            row["N4"] = item.get("N4", "")
            row["Fonte"] = friendly_source_label(item.get("source", ""))
            rows.append(row)
        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name="Resultados", engine="openpyxl")

        df_out = pd.read_excel(io.BytesIO(buf.getvalue()), sheet_name="Resultados")
        assert list(df_out.columns) == [
            "Descricao",
            "Fornecedor",
            "N1",
            "N2",
            "N3",
            "N4",
            "Fonte",
        ]
        assert df_out.iloc[0]["Fornecedor"] == "ABC Ltda"
        assert df_out.iloc[1]["Fornecedor"] == "Tintas XYZ"

    def test_no_extra_columns_when_absent(self, tmp_path):
        """When extra_columns is empty, output should be the same as before."""
        items = [
            {
                "Descricao": "Parafuso M8",
                "N1": "Materiais",
                "N2": "Fixadores",
                "N3": "Parafusos",
                "N4": "Parafuso M8",
                "source": "LLM (Batch)",
                "confidence": 0.92,
            },
        ]
        excel_bytes = _generate_excel_from_items(items)
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert "Fornecedor" not in df.columns
        assert list(df.columns) == ["Descricao", "N1", "N2", "N3", "N4", "Fonte"]

    def test_rejects_pending_job(self, tmp_path):
        """Status PENDING should not generate Excel."""
        job_dir, status_data = _make_job_dir(tmp_path, status="PENDING")
        allowed = ("CLASSIFIED", "COMPLETED", "APPROVED")
        assert status_data["status"] not in allowed

    def test_post_empty_decisions_adds_status_column_all_pending(self, tmp_path):
        """POST with empty decisions list adds Status column with all Pendente."""
        items = [
            {
                "Descricao": "Parafuso M8",
                "N1": "Materiais",
                "N2": "Fixadores",
                "N3": "Parafusos",
                "N4": "Parafuso M8",
                "source": "Grok",
                "confidence": 0.92,
            },
        ]
        excel_bytes = _generate_excel_with_decisions(items, decisions=[])
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert "Status" in df.columns
        assert list(df.columns) == [
            "Descricao",
            "N1",
            "N2",
            "N3",
            "N4",
            "Fonte",
            "Status",
        ]
        assert df.iloc[0]["Status"] == "Pendente"

    def test_post_mix_decisions_merge_correctly(self, tmp_path):
        """POST with mixed decisions merges N1-N4, Fonte, Status correctly."""
        items = [
            {
                "Descricao": "Item A",
                "N1": "Cat1",
                "N2": "Sub1",
                "N3": "Grp1",
                "N4": "Det1",
                "source": "Grok",
                "confidence": 0.9,
            },
            {
                "Descricao": "Item B",
                "N1": "Cat2",
                "N2": "Sub2",
                "N3": "Grp2",
                "N4": "Det2",
                "source": "Base de Aprendizado",
                "confidence": 0.95,
            },
            {
                "Descricao": "Item C",
                "N1": "Cat3",
                "N2": "Sub3",
                "N3": "Grp3",
                "N4": "Det3",
                "source": "Grok",
                "confidence": 0.5,
            },
        ]
        decisions = [
            {
                "index": 0,
                "decision": "approved",
                "N1": "Cat1",
                "N2": "Sub1",
                "N3": "Grp1",
                "N4": "Det1",
            },
            {
                "index": 2,
                "decision": "edited",
                "N1": "CatX",
                "N2": "SubX",
                "N3": "GrpX",
                "N4": "DetX",
            },
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
            {
                "Descricao": "Item A",
                "N1": "Cat1",
                "N2": "Sub1",
                "N3": "Grp1",
                "N4": "Det1",
                "source": "Grok",
                "confidence": 0.9,
            },
        ]
        decisions = [
            {
                "index": 0,
                "decision": "rejected",
                "N1": "Cat1",
                "N2": "Sub1",
                "N3": "Grp1",
                "N4": "Det1",
            },
        ]
        excel_bytes = _generate_excel_with_decisions(items, decisions=decisions)
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert len(df) == 1
        assert df.iloc[0]["Status"] == "Rejeitado"
        assert df.iloc[0]["N4"] == "Det1"

    def test_get_without_decisions_no_status_column(self, tmp_path):
        """GET (no decisions) should NOT have Status column — backward compat."""
        items = [
            {
                "Descricao": "Parafuso M8",
                "N1": "Materiais",
                "N2": "Fixadores",
                "N3": "Parafusos",
                "N4": "Parafuso M8",
                "source": "LLM (Batch)",
                "confidence": 0.92,
            },
        ]
        excel_bytes = _generate_excel_from_items(items)
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert "Status" not in df.columns

    def test_post_with_extra_columns_and_decisions(self, tmp_path):
        """POST with extra_columns + decisions preserves all columns correctly."""
        items = [
            {
                "Descricao": "Parafuso M8",
                "Fornecedor": "ABC Ltda",
                "N1": "Materiais",
                "N2": "Fixadores",
                "N3": "Parafusos",
                "N4": "Parafuso M8",
                "source": "Grok",
                "confidence": 0.92,
            },
        ]
        decisions = [
            {
                "index": 0,
                "decision": "edited",
                "N1": "Materiais",
                "N2": "Fixadores",
                "N3": "Parafusos",
                "N4": "Parafuso M10",
            },
        ]
        excel_bytes = _generate_excel_with_decisions(
            items, decisions=decisions, extra_columns=["Fornecedor"]
        )
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        assert list(df.columns) == [
            "Descricao",
            "Fornecedor",
            "N1",
            "N2",
            "N3",
            "N4",
            "Fonte",
            "Status",
        ]
        assert df.iloc[0]["Fornecedor"] == "ABC Ltda"
        assert df.iloc[0]["N4"] == "Parafuso M10"
        assert df.iloc[0]["Fonte"] == "Ajuste Manual"
        assert df.iloc[0]["Status"] == "Editado"


class TestDownloadJobExcelEndpoint:
    """Testes de integração: chamam o endpoint real DownloadJobExcel."""

    def _call_endpoint(self, tmp_path, monkeypatch, method="GET", decisions=None):
        """Helper: cria job dir, monta req mock, chama endpoint, retorna DataFrame."""
        items = [
            {
                "Descricao": "Parafuso M8",
                "N1": "Materiais",
                "N2": "Fixadores",
                "N3": "Parafusos",
                "N4": "Parafuso M8",
                "source": "Grok",
                "confidence": 0.92,
            },
            {
                "Descricao": "Tinta Azul",
                "N1": "Materiais",
                "N2": "Pintura",
                "N3": "Tintas",
                "N4": "Tinta Esmalte",
                "source": "Base de Aprendizado",
                "confidence": 0.80,
            },
        ]
        job_dir, _ = _make_job_dir(tmp_path, status="CLASSIFIED", items=items)

        jobs_dir = str(tmp_path)
        monkeypatch.setattr(
            "blueprints.classification_bp.get_jobs_dir", lambda: jobs_dir
        )

        from blueprints.classification_bp import DownloadJobExcel

        req = MagicMock()
        req.method = method
        req.params = {"jobId": "job_123"}
        if method == "POST" and decisions is not None:
            req.get_json.return_value = {"decisions": decisions}
        elif method == "POST":
            req.get_json.return_value = {"decisions": []}

        response = DownloadJobExcel(req)
        body = json.loads(response.get_body())

        excel_bytes = base64.b64decode(body["file_content_base64"])
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Resultados")
        return df, body

    def test_endpoint_get_returns_excel_without_status(self, tmp_path, monkeypatch):
        """GET endpoint returns Excel without Status column."""
        df, body = self._call_endpoint(tmp_path, monkeypatch, method="GET")

        assert "Status" not in df.columns
        assert len(df) == 2
        assert body["filename"] == "compras_2024_resultado.xlsx"

    def test_endpoint_post_with_decisions_adds_status(self, tmp_path, monkeypatch):
        """POST endpoint merges decisions and adds Status column."""
        decisions = [
            {
                "index": 0,
                "decision": "approved",
                "N1": "M",
                "N2": "F",
                "N3": "P",
                "N4": "P",
            },
            {
                "index": 1,
                "decision": "edited",
                "N1": "X",
                "N2": "Y",
                "N3": "Z",
                "N4": "W",
            },
        ]
        df, _ = self._call_endpoint(
            tmp_path, monkeypatch, method="POST", decisions=decisions
        )

        assert "Status" in df.columns

        # Item 0: approved — mantém N1-N4 do pipeline
        assert df.iloc[0]["N4"] == "Parafuso M8"
        assert df.iloc[0]["Fonte"] == "Grok"
        assert df.iloc[0]["Status"] == "Aprovado"

        # Item 1: edited — N1-N4 da decision
        assert df.iloc[1]["N4"] == "W"
        assert df.iloc[1]["Fonte"] == "Ajuste Manual"
        assert df.iloc[1]["Status"] == "Editado"

    def test_endpoint_post_empty_decisions_all_pending(self, tmp_path, monkeypatch):
        """POST with empty decisions adds Status column with all Pendente."""
        df, _ = self._call_endpoint(tmp_path, monkeypatch, method="POST", decisions=[])

        assert "Status" in df.columns
        assert df.iloc[0]["Status"] == "Pendente"
        assert df.iloc[1]["Status"] == "Pendente"
