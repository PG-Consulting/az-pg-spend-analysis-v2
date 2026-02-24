"""Tests for src.core_classification — Two-Phase KB Learning pipeline.

All tests mock classify_items_with_llm to avoid real Grok/xAI calls.
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from src.core_classification import (
    process_dataframe_chunk,
    _llm_direct_pipeline,
    KB_DIRECT_MATCH_THRESHOLD,
    KB_ENRICHED_MAX_EXAMPLES,
)
from src.kb_retriever import KBRetriever
from src.knowledge_base import merge_kb_entries


# ---------------------------------------------------------------------------
# Fixture: KB entries that produce high similarity for known descriptions
# ---------------------------------------------------------------------------

KB_ENTRIES = [
    {
        "description_norm": "parafuso sextavado m8 inox",
        "description": "Parafuso Sextavado M8 Inox",
        "N1": "Materiais",
        "N2": "Fixação",
        "N3": "Parafusos",
        "N4": "Parafuso Sextavado",
        "source": "consultant_correction",
        "confidence": 0.95,
    },
    {
        "description_norm": "oleo lubrificante motor diesel",
        "description": "Óleo Lubrificante Motor Diesel",
        "N1": "MRO",
        "N2": "Lubrificação",
        "N3": "Óleos",
        "N4": "Óleo Motor",
        "source": "llm_approved",
        "confidence": 0.85,
    },
    {
        "description_norm": "filtro ar compressor industrial",
        "description": "Filtro de Ar Compressor Industrial",
        "N1": "MRO",
        "N2": "Filtração",
        "N3": "Filtros",
        "N4": "Filtro de Ar",
        "source": "llm_approved",
        "confidence": 0.80,
    },
    {
        "description_norm": "bomba centrifuga agua salgada",
        "description": "Bomba Centrífuga Água Salgada",
        "N1": "Equipamentos",
        "N2": "Bombas",
        "N3": "Centrífugas",
        "N4": "Bomba Água",
        "source": "consultant_correction",
        "confidence": 0.90,
    },
]


@pytest.fixture
def kb_entries():
    import copy
    return copy.deepcopy(KB_ENTRIES)


@pytest.fixture
def kb_retriever(kb_entries):
    return KBRetriever(kb_entries)


def _make_llm_result(desc, n4="LLM Category"):
    """Helper to create a mock LLM result."""
    return {
        "N1": "LLM-N1",
        "N2": "LLM-N2",
        "N3": "LLM-N3",
        "N4": n4,
        "source": "LLM (Batch)",
        "confidence": 0.75,
    }


# ---------------------------------------------------------------------------
# Tests: KB direct match (Phase 1)
# ---------------------------------------------------------------------------

class TestKBDirectMatch:
    @patch("src.llm_classifier.classify_items_with_llm")
    def test_kb_direct_match_skips_llm(self, mock_llm, kb_entries, kb_retriever):
        """Items with near-identical KB matches (sim >= 0.90) skip LLM entirely."""
        # Query with exact same text as KB entry → should get similarity ~1.0
        descriptions = ["parafuso sextavado m8 inox"]

        mock_llm.return_value = []  # Should not be called

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=kb_entries,
            hierarchy_lookup=None,
            kb_retriever=kb_retriever,
        )

        assert len(results) == 1
        assert results[0]["source"] == "KB (Direct Match)"
        assert results[0]["N4"] == "Parafuso Sextavado"
        assert results[0]["confidence"] >= KB_DIRECT_MATCH_THRESHOLD
        # LLM should NOT have been called (all items resolved by KB)
        mock_llm.assert_not_called()

    @patch("src.llm_classifier.classify_items_with_llm")
    def test_kb_direct_match_skips_nao_identificado(self, mock_llm):
        """KB entries with 'Não Identificado' in N4 should NOT be used as direct match."""
        bad_kb = [
            {
                "description_norm": "servico transporte pessoas",
                "description": "Servico Transporte Pessoas",
                "N1": "Serviços",
                "N2": "Transporte",
                "N3": "Passageiros",
                "N4": "Não Identificado",
                "source": "llm_approved",
                "confidence": 0.85,
            },
        ]
        retriever = KBRetriever(bad_kb)

        descriptions = ["servico transporte pessoas"]
        mock_llm.return_value = [_make_llm_result(descriptions[0], "Transporte Rodoviário")]

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=bad_kb,
            hierarchy_lookup=None,
            kb_retriever=retriever,
        )

        assert len(results) == 1
        # Should NOT be KB Direct Match — should fall through to LLM
        assert results[0]["source"] == "LLM (Batch)"
        assert results[0]["N4"] == "Transporte Rodoviário"
        mock_llm.assert_called_once()

    @patch("src.llm_classifier.classify_items_with_llm")
    def test_kb_direct_match_confidence_is_similarity(self, mock_llm, kb_entries, kb_retriever):
        """KB direct match confidence should be the cosine similarity score."""
        descriptions = ["parafuso sextavado m8 inox"]
        mock_llm.return_value = []

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=kb_entries,
            hierarchy_lookup=None,
            kb_retriever=kb_retriever,
        )

        # Confidence is the similarity score (rounded to 3 decimals)
        assert results[0]["confidence"] > 0.0
        assert isinstance(results[0]["confidence"], float)


# ---------------------------------------------------------------------------
# Tests: Items sent to LLM (Phase 2)
# ---------------------------------------------------------------------------

class TestRemainingItemsSentToLLM:
    @patch("src.llm_classifier.classify_items_with_llm")
    def test_unrelated_items_go_to_llm(self, mock_llm, kb_entries, kb_retriever):
        """Items with no KB match should be sent to LLM."""
        descriptions = ["computador laptop dell latitude"]

        mock_llm.return_value = [_make_llm_result(descriptions[0], "Laptop")]

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=kb_entries,
            hierarchy_lookup=None,
            kb_retriever=kb_retriever,
        )

        assert len(results) == 1
        assert results[0]["source"] == "LLM (Batch)"
        assert results[0]["N4"] == "Laptop"
        mock_llm.assert_called_once()
        # LLM should have received 1 description
        assert len(mock_llm.call_args[0][0]) == 1

    @patch("src.llm_classifier.classify_items_with_llm")
    def test_no_kb_retriever_sends_all_to_llm(self, mock_llm, kb_entries):
        """Without a kb_retriever, all items go directly to LLM (backward compatible)."""
        descriptions = ["parafuso sextavado m8 inox", "computador laptop dell"]

        mock_llm.return_value = [
            _make_llm_result(d) for d in descriptions
        ]

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=kb_entries,
            hierarchy_lookup=None,
            kb_retriever=None,  # No retriever
        )

        assert len(results) == 2
        # All results should come from LLM
        for r in results:
            assert r["source"] == "LLM (Batch)"
        mock_llm.assert_called_once()
        assert len(mock_llm.call_args[0][0]) == 2


# ---------------------------------------------------------------------------
# Tests: Mixed batch (Phase 1 + Phase 2)
# ---------------------------------------------------------------------------

class TestMixedBatch:
    @patch("src.llm_classifier.classify_items_with_llm")
    def test_mixed_batch_splits_correctly(self, mock_llm, kb_entries, kb_retriever):
        """Batch with mix of KB-matched and unmatched items processes correctly."""
        descriptions = [
            "parafuso sextavado m8 inox",       # Should match KB (sim ~1.0)
            "computador laptop dell latitude",   # No KB match → LLM
            "oleo lubrificante motor diesel",    # Should match KB (sim ~1.0)
        ]

        # LLM should only receive the 1 unmatched item
        mock_llm.return_value = [_make_llm_result("computador laptop dell latitude", "Laptop")]

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=kb_entries,
            hierarchy_lookup=None,
            kb_retriever=kb_retriever,
        )

        assert len(results) == 3

        # Item 0: KB direct match (parafuso)
        assert results[0]["source"] == "KB (Direct Match)"
        assert results[0]["N4"] == "Parafuso Sextavado"

        # Item 1: LLM (computador)
        assert results[1]["source"] == "LLM (Batch)"
        assert results[1]["N4"] == "Laptop"

        # Item 2: KB direct match (oleo)
        assert results[2]["source"] == "KB (Direct Match)"
        assert results[2]["N4"] == "Óleo Motor"

        # LLM received only 1 description (the unmatched one)
        mock_llm.assert_called_once()
        llm_descriptions = mock_llm.call_args[0][0]
        assert len(llm_descriptions) == 1
        assert "computador" in llm_descriptions[0].lower()

    @patch("src.llm_classifier.classify_items_with_llm")
    def test_all_kb_matched_no_llm_call(self, mock_llm, kb_entries, kb_retriever):
        """When all items match KB, LLM should not be called at all."""
        descriptions = [
            "parafuso sextavado m8 inox",
            "oleo lubrificante motor diesel",
        ]

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=kb_entries,
            hierarchy_lookup=None,
            kb_retriever=kb_retriever,
        )

        assert len(results) == 2
        assert all(r["source"] == "KB (Direct Match)" for r in results)
        mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: process_dataframe_chunk integration
# ---------------------------------------------------------------------------

class TestProcessDataframeChunkWithKBRetriever:
    @patch("src.llm_classifier.classify_items_with_llm")
    def test_process_dataframe_chunk_passes_kb_retriever(self, mock_llm, kb_entries, kb_retriever):
        """process_dataframe_chunk passes kb_retriever through to _llm_direct_pipeline."""
        df = pd.DataFrame({"Descricao": ["parafuso sextavado m8 inox"]})

        mock_llm.return_value = []

        results = process_dataframe_chunk(
            df,
            desc_column="Descricao",
            few_shot_examples=kb_entries,
            kb_retriever=kb_retriever,
        )

        assert len(results) == 1
        assert results[0]["source"] == "KB (Direct Match)"
        mock_llm.assert_not_called()

    @patch("src.llm_classifier.classify_items_with_llm")
    def test_process_dataframe_chunk_without_kb_retriever(self, mock_llm, kb_entries):
        """process_dataframe_chunk without kb_retriever sends all to LLM (backward compat)."""
        df = pd.DataFrame({"Descricao": ["parafuso sextavado m8 inox"]})

        mock_llm.return_value = [_make_llm_result("parafuso", "Parafusos")]

        results = process_dataframe_chunk(
            df,
            desc_column="Descricao",
            few_shot_examples=kb_entries,
        )

        assert len(results) == 1
        assert results[0]["source"] == "LLM (Batch)"
        mock_llm.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Enriched examples passed to LLM
# ---------------------------------------------------------------------------

class TestEnrichedExamples:
    @patch("src.llm_classifier.classify_items_with_llm")
    def test_llm_receives_enriched_examples(self, mock_llm, kb_entries, kb_retriever):
        """LLM should receive enriched (per-batch relevant) examples, not global ones."""
        # "filtro ar compressor" has a partial match in KB but not exact (sim < 0.90)
        # so it goes to LLM, but with enriched examples from the KB
        descriptions = ["filtro ar industrial para compressor de ar"]

        mock_llm.return_value = [_make_llm_result(descriptions[0], "Filtro Ar")]

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=kb_entries,
            hierarchy_lookup=None,
            kb_retriever=kb_retriever,
        )

        mock_llm.assert_called_once()
        # Check that few_shot_examples were passed (enriched or fallback)
        call_kwargs = mock_llm.call_args[1]
        examples = call_kwargs.get("few_shot_examples")
        assert examples is not None
        assert len(examples) > 0

    @patch("src.llm_classifier.classify_items_with_llm")
    def test_fallback_to_global_examples_when_no_matches(self, mock_llm):
        """When kb_retriever has no matches, falls back to global representative examples."""
        descriptions = ["xyz completely unrelated thing"]

        few_shot = [
            {"description_norm": "item a", "N4": "Cat A", "source": "llm_approved", "confidence": 0.8},
            {"description_norm": "item b", "N4": "Cat B", "source": "llm_approved", "confidence": 0.7},
        ]

        # Create retriever with entries that won't match
        retriever = KBRetriever(few_shot)
        mock_llm.return_value = [_make_llm_result(descriptions[0])]

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=few_shot,
            hierarchy_lookup=None,
            kb_retriever=retriever,
        )

        mock_llm.assert_called_once()
        # Should have received some examples (global fallback)
        call_kwargs = mock_llm.call_args[1]
        examples = call_kwargs.get("few_shot_examples")
        assert examples is not None


# ---------------------------------------------------------------------------
# Tests: Confidence zeroed for "Não Identificado"
# ---------------------------------------------------------------------------

class TestNaoIdentificadoConfidence:
    @patch("src.llm_classifier.classify_items_with_llm")
    def test_nao_identificado_n4_gets_zero_confidence(self, mock_llm):
        """Items where LLM returns empty N4 (filled as 'Não Identificado') get confidence=0."""
        descriptions = ["servico transporte de pessoas"]

        # LLM returns N1-N3 but empty N4 with high confidence
        mock_llm.return_value = [{
            "N1": "Serviços",
            "N2": "Transporte e Logística",
            "N3": "Transporte de Passageiros",
            "N4": "Não Identificado",
            "source": "LLM (Batch)",
            "confidence": 0.95,
        }]

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=None,
            hierarchy_lookup=None,
        )

        assert len(results) == 1
        assert results[0]["N4"] == "Não Identificado"
        assert results[0]["confidence"] == 0.0  # Must be zero, not 0.95

    @patch("src.llm_classifier.classify_items_with_llm")
    def test_complete_classification_keeps_confidence(self, mock_llm):
        """Items with all N1-N4 filled keep their original confidence."""
        descriptions = ["parafuso sextavado m8"]

        mock_llm.return_value = [{
            "N1": "MRO",
            "N2": "Fixação",
            "N3": "Parafusos",
            "N4": "Parafuso Sextavado",
            "source": "LLM (Batch)",
            "confidence": 0.92,
        }]

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=None,
            hierarchy_lookup=None,
        )

        assert len(results) == 1
        assert results[0]["N4"] == "Parafuso Sextavado"
        assert results[0]["confidence"] == 0.92  # Preserved


# ---------------------------------------------------------------------------
# Tests: Merged KB (sector + project) in pipeline
# ---------------------------------------------------------------------------

class TestMergedKBInPipeline:
    @patch("src.llm_classifier.classify_items_with_llm")
    def test_sector_entry_used_as_direct_match(self, mock_llm):
        """Sector KB entries merged with project should be usable for direct match."""
        # Sector has "parafuso" entry, project has "oleo" entry
        sector_entries = [
            {
                "description_norm": "parafuso sextavado m8 inox",
                "description": "Parafuso Sextavado M8 Inox",
                "N1": "Materiais",
                "N2": "Fixação",
                "N3": "Parafusos",
                "N4": "Parafuso Sextavado",
                "source": "consultant_correction",
                "confidence": 0.95,
            },
        ]
        project_entries = [
            {
                "description_norm": "oleo lubrificante motor diesel",
                "description": "Óleo Lubrificante Motor Diesel",
                "N1": "MRO",
                "N2": "Lubrificação",
                "N3": "Óleos",
                "N4": "Óleo Motor",
                "source": "llm_approved",
                "confidence": 0.85,
            },
        ]

        merged = merge_kb_entries(sector_entries, project_entries)
        retriever = KBRetriever(merged)

        descriptions = ["parafuso sextavado m8 inox"]
        mock_llm.return_value = []

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=merged,
            hierarchy_lookup=None,
            kb_retriever=retriever,
        )

        assert len(results) == 1
        assert results[0]["source"] == "KB (Direct Match)"
        assert results[0]["N4"] == "Parafuso Sextavado"
        mock_llm.assert_not_called()

    @patch("src.llm_classifier.classify_items_with_llm")
    def test_project_overrides_sector_in_merged_kb(self, mock_llm):
        """When both sector and project have same description, project version is used."""
        sector_entries = [
            {
                "description_norm": "parafuso sextavado m8 inox",
                "description": "Parafuso Sextavado M8 Inox",
                "N1": "Materiais",
                "N2": "Fixação",
                "N3": "Parafusos",
                "N4": "Sector Category",  # sector classification
                "source": "llm_approved",
                "confidence": 0.80,
            },
            {
                "description_norm": "filtro ar compressor industrial",
                "description": "Filtro de Ar Compressor Industrial",
                "N1": "MRO",
                "N2": "Filtração",
                "N3": "Filtros",
                "N4": "Filtro de Ar",
                "source": "llm_approved",
                "confidence": 0.80,
            },
        ]
        project_entries = [
            {
                "description_norm": "parafuso sextavado m8 inox",
                "description": "Parafuso Sextavado M8 Inox",
                "N1": "Materiais",
                "N2": "Fixação",
                "N3": "Parafusos",
                "N4": "Project Category",  # project override
                "source": "consultant_correction",
                "confidence": 0.95,
            },
        ]

        merged = merge_kb_entries(sector_entries, project_entries)
        # Sector had 2 entries, project overrides 1 → merged has 2
        assert len(merged) == 2
        # The parafuso entry should be the project version
        parafuso_entry = [e for e in merged if "parafuso" in e["description_norm"]][0]
        assert parafuso_entry["N4"] == "Project Category"

        retriever = KBRetriever(merged)

        descriptions = ["parafuso sextavado m8 inox"]
        mock_llm.return_value = []

        results = _llm_direct_pipeline(
            descriptions,
            sector="Padrao",
            client_context="",
            custom_hierarchy=None,
            few_shot_examples=merged,
            hierarchy_lookup=None,
            kb_retriever=retriever,
        )

        assert len(results) == 1
        assert results[0]["N4"] == "Project Category"  # project overrides sector
        mock_llm.assert_not_called()
