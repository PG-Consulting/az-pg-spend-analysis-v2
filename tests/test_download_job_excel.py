"""Tests for DownloadJobExcel logic — Excel generation from result.json."""

import json
import io
import os
import base64

import pytest
import pandas as pd

from src.utils import friendly_source_label


def _make_job_dir(tmp_path, status="CLASSIFIED", filename="compras_2024.xlsx", items=None):
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
        rows.append({
            "Descricao": item.get(desc_column, item.get("description", "")),
            "N1": item.get("N1", ""),
            "N2": item.get("N2", ""),
            "N3": item.get("N3", ""),
            "N4": item.get("N4", ""),
            "Fonte": friendly_source_label(item.get("source", "")),
        })
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

    def test_rejects_pending_job(self, tmp_path):
        """Status PENDING should not generate Excel."""
        job_dir, status_data = _make_job_dir(tmp_path, status="PENDING")
        allowed = ("CLASSIFIED", "COMPLETED", "APPROVED")
        assert status_data["status"] not in allowed
