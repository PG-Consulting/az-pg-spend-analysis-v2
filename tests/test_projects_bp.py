"""Tests for project hierarchy resolution — parsing b64 Excel into custom_hierarchy."""
import io
import base64
import pytest

from src.project_manager import parse_hierarchy_from_b64, resolve_hierarchy_from_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hierarchy_excel_b64():
    """Create a minimal Excel file with N1-N4 hierarchy and return as base64."""
    import pandas as pd

    data = [
        {"N1": "Operação", "N2": "Materiais", "N3": "OEM", "N4": "Peças ABB"},
        {"N1": "Operação", "N2": "Materiais", "N3": "OEM", "N4": "Peças Siemens"},
        {"N1": "Projetos", "N2": "Civil", "N3": "Fundações", "N4": "Estacas"},
    ]
    df = pd.DataFrame(data)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ---------------------------------------------------------------------------
# parse_hierarchy_from_b64
# ---------------------------------------------------------------------------

class TestParseHierarchyFromB64:

    def test_parses_valid_excel(self):
        b64 = _make_hierarchy_excel_b64()
        result = parse_hierarchy_from_b64(b64)
        assert result is not None
        assert len(result) == 3
        assert result[0]["N1"] == "Operação"
        assert result[2]["N4"] == "Estacas"

    def test_returns_none_for_empty_string(self):
        assert parse_hierarchy_from_b64("") is None

    def test_returns_none_for_none(self):
        assert parse_hierarchy_from_b64(None) is None

    def test_returns_none_for_invalid_data(self):
        bad_b64 = base64.b64encode(b"not an excel file").decode()
        assert parse_hierarchy_from_b64(bad_b64) is None


# ---------------------------------------------------------------------------
# resolve_hierarchy_from_body
# ---------------------------------------------------------------------------

class TestResolveHierarchyFromBody:

    def test_parses_hierarchy_file_b64(self):
        """Frontend sends hierarchy_file_base64 → should be parsed into custom_hierarchy."""
        b64 = _make_hierarchy_excel_b64()
        body = {
            "display_name": "Test Project",
            "sector": "test",
            "hierarchy_file_base64": b64,
            "hierarchy_source": "own",
        }
        resolve_hierarchy_from_body(body)

        assert body["custom_hierarchy"] is not None
        assert len(body["custom_hierarchy"]) == 3
        assert body["hierarchy_source"] == "own"
        assert "hierarchy_file_base64" not in body  # should be popped

    def test_existing_custom_hierarchy_takes_precedence(self):
        """If custom_hierarchy is already a list, don't touch it."""
        existing = [{"N1": "A", "N2": "B", "N3": "C", "N4": "D"}]
        body = {
            "custom_hierarchy": existing,
            "hierarchy_file_base64": "should_be_ignored",
        }
        resolve_hierarchy_from_body(body)
        assert body["custom_hierarchy"] == existing

    def test_no_hierarchy_sets_padrao(self):
        """No hierarchy provided → hierarchy_source defaults to 'padrao'."""
        body = {"display_name": "Test", "sector": "test"}
        resolve_hierarchy_from_body(body)
        assert body["hierarchy_source"] == "padrao"

    def test_no_hierarchy_preserves_explicit_source(self):
        """If caller explicitly sets hierarchy_source, preserve it."""
        body = {"display_name": "Test", "sector": "test", "hierarchy_source": "own"}
        resolve_hierarchy_from_body(body)
        # setdefault won't overwrite existing "own"
        assert body["hierarchy_source"] == "own"

    def test_failed_b64_parse_sets_padrao(self):
        """Invalid b64 file → fallback to padrao."""
        bad_b64 = base64.b64encode(b"garbage").decode()
        body = {
            "display_name": "Test",
            "sector": "test",
            "hierarchy_file_base64": bad_b64,
        }
        resolve_hierarchy_from_body(body)
        assert body.get("custom_hierarchy") is None or body.get("custom_hierarchy") == []
        assert body["hierarchy_source"] == "padrao"

    def test_b64_removed_from_body(self):
        """hierarchy_file_base64 should be popped (not stored in project config)."""
        b64 = _make_hierarchy_excel_b64()
        body = {"hierarchy_file_base64": b64}
        resolve_hierarchy_from_body(body)
        assert "hierarchy_file_base64" not in body
