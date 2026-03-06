"""Tests for src.utils — safe_json_dumps, get_models_dir, get_sectors_dir."""

import json
import os

import pytest

from src.utils import safe_json_dumps, get_models_dir, get_sectors_dir, friendly_source_label, INCOMPLETE_VALUES


# ============================================================
# safe_json_dumps
# ============================================================

class TestSafeJsonDumps:
    def test_safe_json_dumps_basic(self):
        data = {"key": "value", "count": 42}
        result = safe_json_dumps(data)
        parsed = json.loads(result)
        assert parsed == data

    def test_safe_json_dumps_nan(self):
        data = {"score": float("nan")}
        result = safe_json_dumps(data)
        parsed = json.loads(result)
        assert parsed["score"] is None

    def test_safe_json_dumps_inf(self):
        data = {"value": float("inf")}
        result = safe_json_dumps(data)
        parsed = json.loads(result)
        assert parsed["value"] is None

    def test_safe_json_dumps_nested(self):
        data = {"outer": {"inner": float("nan"), "ok": 1.5}}
        result = safe_json_dumps(data)
        parsed = json.loads(result)
        assert parsed["outer"]["inner"] is None
        assert parsed["outer"]["ok"] == 1.5

    def test_safe_json_dumps_list(self):
        data = [1.0, float("nan"), 3.0, float("-inf")]
        result = safe_json_dumps(data)
        parsed = json.loads(result)
        assert parsed == [1.0, None, 3.0, None]


# ============================================================
# get_models_dir
# ============================================================

class TestGetModelsDir:
    def test_get_models_dir_env_override(self, monkeypatch, tmp_path):
        """When MODELS_DIR_PATH env var is set, use that path directly."""
        custom_dir = str(tmp_path / "custom_models")
        monkeypatch.setenv("MODELS_DIR_PATH", custom_dir)
        result = get_models_dir()
        assert result == custom_dir

    def test_get_models_dir_local_fallback(self, monkeypatch):
        """When no env var and /mount/models does not exist, create and return local ./models."""
        monkeypatch.delenv("MODELS_DIR_PATH", raising=False)
        # /mount/models should not exist on a dev machine
        result = get_models_dir()
        # Should end with 'models' and be relative to the project root (two dirs up from src/utils.py)
        assert result.endswith("models")
        assert os.path.isdir(result)


# ============================================================
# get_sectors_dir
# ============================================================

class TestGetSectorsDir:
    def test_get_sectors_dir(self, monkeypatch, tmp_path):
        """get_sectors_dir returns models_dir + '/sectors'."""
        models_dir = str(tmp_path / "test_models")
        monkeypatch.setenv("MODELS_DIR_PATH", models_dir)
        result = get_sectors_dir()
        assert result == os.path.join(models_dir, "sectors")


# ============================================================
# friendly_source_label
# ============================================================

class TestIncompleteValues:
    """INCOMPLETE_VALUES deve incluir variantes de NaN/None/null."""

    def test_nan_variants_in_incomplete(self):
        for val in ("nan", "NaN", "None", "none", "null", "NULL"):
            assert val in INCOMPLETE_VALUES, f"'{val}' deveria estar em INCOMPLETE_VALUES"

    def test_standard_values_still_present(self):
        assert "" in INCOMPLETE_VALUES
        assert "Não Identificado" in INCOMPLETE_VALUES
        assert "Nao Identificado" in INCOMPLETE_VALUES

    def test_valid_categories_not_incomplete(self):
        assert "Materiais" not in INCOMPLETE_VALUES
        assert "Serviços" not in INCOMPLETE_VALUES


class TestFriendlySourceLabel:
    def test_friendly_source_label_reclassified_with_guidance(self):
        assert friendly_source_label("reclassified_with_guidance") == "Reclassificado"

    def test_friendly_source_label_known_sources(self):
        assert friendly_source_label("KB (Direct Match)") == "Base de Aprendizado"
        assert friendly_source_label("LLM (Batch)") == "Grok"
        assert friendly_source_label("consultant_correction") == "Ajuste Manual"

    def test_friendly_source_label_unknown_passthrough(self):
        assert friendly_source_label("unknown_source") == "unknown_source"
        assert friendly_source_label("") == ""
