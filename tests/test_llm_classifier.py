"""Tests for src.llm_classifier — fallback chunk size and prompt correctness."""
import pytest
from unittest.mock import patch, MagicMock

from src.llm_classifier import classify_items_with_llm, _call_openai_api
import inspect


FAKE_CONFIG = {"endpoint": "https://fake.api/v1", "api_key": "fake-key-1234567890", "deployment": "grok-test"}


class TestFallbackChunkSize:
    """Quando um chunk falha, o fallback deve usar o tamanho real do chunk que falhou,
    não o tamanho do primeiro chunk."""

    @patch("src.llm_classifier.get_azure_openai_config", return_value=FAKE_CONFIG)
    @patch("src.llm_classifier._call_openai_api")
    def test_last_chunk_fallback_uses_correct_size(self, mock_api, mock_config):
        """Se o último chunk (menor) falhar, fallback deve gerar apenas len(last_chunk) items,
        não len(first_chunk) items."""
        # 150 items => chunk_size=100 => 2 chunks: [0:100] (100 items) + [100:150] (50 items)
        descriptions = [f"item_{i}" for i in range(150)]

        def side_effect(items, *args, **kwargs):
            # First chunk (100 items) succeeds
            if len(items) == 100:
                results = [
                    {"N1": "Cat", "N2": "Sub", "N3": "Grp", "N4": "Det",
                     "confidence": 0.9, "LLM_Explanation": "ok"}
                    for _ in items
                ]
                return results, {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0}
            # Second chunk (50 items) fails
            raise RuntimeError("API Error on last chunk")

        mock_api.side_effect = side_effect
        results = classify_items_with_llm(descriptions)

        assert len(results) == 150
        # First 100 should be successful classifications
        for i in range(100):
            assert results[i]["N1"] == "Cat", f"Item {i} should be classified"
        # Last 50 should be fallback
        for i in range(100, 150):
            assert results[i]["N1"] == "Não Identificado", f"Item {i} should be fallback"
            assert results[i]["confidence"] == 0.0

    @patch("src.llm_classifier.get_azure_openai_config", return_value=FAKE_CONFIG)
    @patch("src.llm_classifier._call_openai_api")
    def test_single_chunk_fallback(self, mock_api, mock_config):
        """Se o único chunk falhar, fallback cobre todos os items."""
        descriptions = [f"item_{i}" for i in range(50)]
        mock_api.side_effect = RuntimeError("API Error")

        results = classify_items_with_llm(descriptions)

        assert len(results) == 50
        for r in results:
            assert r["N1"] == "Não Identificado"
            assert r["confidence"] == 0.0


class TestPromptNoOldModelReference:
    """Prompt LLM nao deve referenciar modelo antigo grok-4-0709."""

    def test_no_grok_4_0709_in_prompt(self):
        """O source code de _call_openai_api nao deve conter referencia ao modelo antigo."""
        source = inspect.getsource(_call_openai_api)
        assert "grok-4-0709" not in source, (
            "Prompt ainda referencia modelo antigo 'grok-4-0709'. "
            "Remover referencia hardcoded a modelo especifico."
        )

    def test_prompt_contains_disambiguation_instruction(self):
        """A instrucao de desambiguacao deve existir sem referencia a modelo."""
        source = inspect.getsource(_call_openai_api)
        assert "desambiguar contextos" in source, (
            "Instrucao de desambiguacao deve estar presente no prompt."
        )
