"""Tests for src.kb_retriever.KBRetriever."""

import pytest
from src.kb_retriever import KBRetriever


# ---------------------------------------------------------------------------
# Fixture: sample KB entries
# ---------------------------------------------------------------------------

KB_ENTRIES = [
    {
        "description_norm": "parafuso sextavado m8",
        "description": "Parafuso Sextavado M8",
        "N1": "MRO",
        "N2": "Fixação",
        "N3": "Parafusos",
        "N4": "Parafuso Sextavado",
        "source": "consultant_correction",
        "confidence": 0.95,
    },
    {
        "description_norm": "oleo lubrificante motor",
        "description": "Óleo Lubrificante Motor",
        "N1": "MRO",
        "N2": "Lubrificação",
        "N3": "Óleos",
        "N4": "Óleo Motor",
        "source": "llm_approved",
        "confidence": 0.85,
    },
    {
        "description_norm": "filtro ar compressor",
        "description": "Filtro de Ar Compressor",
        "N1": "MRO",
        "N2": "Filtração",
        "N3": "Filtros",
        "N4": "Filtro de Ar",
        "source": "llm_approved",
        "confidence": 0.80,
    },
    {
        "description_norm": "bomba centrifuga agua",
        "description": "Bomba Centrífuga Água",
        "N1": "Equipamentos",
        "N2": "Bombas",
        "N3": "Centrífugas",
        "N4": "Bomba Água",
        "source": "consultant_correction",
        "confidence": 0.90,
    },
    {
        "description_norm": "valvula solenoide pneumatica",
        "description": "Válvula Solenóide Pneumática",
        "N1": "Equipamentos",
        "N2": "Válvulas",
        "N3": "Solenóides",
        "N4": "Válvula Pneumática",
        "source": "llm_approved",
        "confidence": 0.75,
    },
]


@pytest.fixture
def kb_entries():
    """Return a fresh copy of KB_ENTRIES to avoid cross-test mutation."""
    import copy
    return copy.deepcopy(KB_ENTRIES)


# ---------------------------------------------------------------------------
# Tests: initialization
# ---------------------------------------------------------------------------

class TestKBRetrieverInit:
    def test_init_empty(self):
        """KBRetriever([]) initializes without error; vectorizer is None."""
        retriever = KBRetriever([])
        assert retriever.vectorizer is None
        assert retriever.matrix is None
        assert retriever.entries == []

    def test_init_with_entries(self, kb_entries):
        """KBRetriever with entries has a fitted vectorizer and matrix."""
        retriever = KBRetriever(kb_entries)
        assert retriever.vectorizer is not None
        assert retriever.matrix is not None
        assert retriever.matrix.shape[0] == len(kb_entries)


# ---------------------------------------------------------------------------
# Tests: retrieve (single query)
# ---------------------------------------------------------------------------

class TestKBRetrieverRetrieve:
    def test_retrieve_similar(self, kb_entries):
        """Querying 'parafuso aço inox m8' should return parafuso entry as most similar."""
        retriever = KBRetriever(kb_entries)
        results = retriever.retrieve("parafuso aço inox m8", top_k=3)

        assert len(results) > 0
        best = results[0]
        assert best["N4"] == "Parafuso Sextavado"
        assert "_similarity" in best
        assert best["_similarity"] > 0.01

    def test_retrieve_unrelated(self, kb_entries):
        """Querying a completely unrelated description returns empty or very low-score results."""
        retriever = KBRetriever(kb_entries)
        results = retriever.retrieve("computador laptop dell", top_k=3)

        # Either empty or all results have low similarity (below typical useful thresholds)
        if results:
            for r in results:
                assert r["_similarity"] < 0.3

    def test_retrieve_top_k_limit(self, kb_entries):
        """top_k=2 returns at most 2 results."""
        retriever = KBRetriever(kb_entries)
        results = retriever.retrieve("parafuso sextavado m8", top_k=2)
        assert len(results) <= 2

    def test_retrieve_empty_kb(self):
        """Retrieving from an empty KB returns an empty list."""
        retriever = KBRetriever([])
        results = retriever.retrieve("parafuso aço", top_k=3)
        assert results == []


# ---------------------------------------------------------------------------
# Tests: retrieve_batch
# ---------------------------------------------------------------------------

class TestKBRetrieverBatch:
    def test_retrieve_batch(self, kb_entries):
        """Batch retrieval of 3 descriptions returns 3 result lists."""
        retriever = KBRetriever(kb_entries)
        descriptions = [
            "parafuso sextavado m8",
            "oleo lubrificante motor diesel",
            "bomba centrifuga industrial",
        ]
        results = retriever.retrieve_batch(descriptions, top_k=3)

        assert len(results) == 3
        for result_list in results:
            assert isinstance(result_list, list)

    def test_retrieve_batch_empty_kb(self):
        """KBRetriever([]).retrieve_batch(['test']) returns [[]]."""
        retriever = KBRetriever([])
        results = retriever.retrieve_batch(["test"])
        assert results == [[]]


# ---------------------------------------------------------------------------
# Tests: select_representative_examples
# ---------------------------------------------------------------------------

class TestKBRetrieverRepresentative:
    def test_select_representative_empty(self):
        """select_representative_examples([]) returns []."""
        result = KBRetriever.select_representative_examples([])
        assert result == []

    def test_select_representative_diverse(self, kb_entries):
        """With entries from different N4s, picks one entry per N4."""
        result = KBRetriever.select_representative_examples(kb_entries, max_k=10)

        # Each N4 should appear at most once
        n4s = [e["N4"] for e in result]
        assert len(n4s) == len(set(n4s))

        # Should have one per unique N4 (5 entries with 5 different N4s)
        unique_n4s = {e["N4"] for e in kb_entries}
        assert len(result) == len(unique_n4s)

    def test_select_representative_max_k(self, kb_entries):
        """max_k=2 returns at most 2 results."""
        result = KBRetriever.select_representative_examples(kb_entries, max_k=2)
        assert len(result) <= 2

    def test_select_representative_prefers_consultant(self, kb_entries):
        """consultant_correction entries are prioritized over llm_approved."""
        result = KBRetriever.select_representative_examples(kb_entries, max_k=5)

        # The consultant_correction entries (parafuso=0.95, bomba=0.90) should come first
        consultant_entries = [e for e in result if e["source"] == "consultant_correction"]
        llm_entries = [e for e in result if e["source"] != "consultant_correction"]

        # All consultant entries should appear before all llm entries in the result
        if consultant_entries and llm_entries:
            last_consultant_idx = max(
                i for i, e in enumerate(result) if e["source"] == "consultant_correction"
            )
            first_llm_idx = min(
                i for i, e in enumerate(result) if e["source"] != "consultant_correction"
            )
            assert last_consultant_idx < first_llm_idx

    def test_select_representative_sorted_by_confidence(self):
        """Within the same source type, higher confidence entries come first."""
        entries = [
            {
                "description_norm": "item a",
                "N4": "Cat A",
                "source": "llm_approved",
                "confidence": 0.60,
            },
            {
                "description_norm": "item b",
                "N4": "Cat B",
                "source": "llm_approved",
                "confidence": 0.90,
            },
            {
                "description_norm": "item c",
                "N4": "Cat C",
                "source": "llm_approved",
                "confidence": 0.75,
            },
        ]
        result = KBRetriever.select_representative_examples(entries, max_k=10)

        # All are llm_approved, so sorted purely by confidence descending
        confidences = [e["confidence"] for e in result]
        assert confidences == sorted(confidences, reverse=True)


# ---------------------------------------------------------------------------
# Tests: select_enriched_examples
# ---------------------------------------------------------------------------

class TestKBRetrieverEnriched:
    def test_select_enriched_examples_basic(self):
        """select_enriched_examples returns deduplicated entries sorted by relevance."""
        batch_results = [
            [
                {"description_norm": "parafuso m8", "N4": "Parafuso", "source": "llm_approved",
                 "confidence": 0.85, "_similarity": 0.80},
                {"description_norm": "oleo motor", "N4": "Óleo Motor", "source": "llm_approved",
                 "confidence": 0.75, "_similarity": 0.50},
            ],
            [
                {"description_norm": "parafuso m8", "N4": "Parafuso", "source": "llm_approved",
                 "confidence": 0.85, "_similarity": 0.90},  # same entry, higher similarity
                {"description_norm": "filtro ar", "N4": "Filtro de Ar", "source": "consultant_correction",
                 "confidence": 0.95, "_similarity": 0.60},
            ],
        ]
        result = KBRetriever.select_enriched_examples(batch_results, max_examples=10)

        # Should have 3 unique entries (parafuso deduped)
        assert len(result) == 3

        # No _similarity key in results
        for entry in result:
            assert "_similarity" not in entry

        # consultant_correction should come first (filtro ar)
        assert result[0]["source"] == "consultant_correction"

    def test_select_enriched_examples_empty(self):
        """select_enriched_examples([]) returns []."""
        assert KBRetriever.select_enriched_examples([]) == []
        assert KBRetriever.select_enriched_examples([[], []]) == []

    def test_select_enriched_examples_max_cap(self):
        """select_enriched_examples respects max_examples limit."""
        # Create 10 unique matches
        batch_results = [[
            {"description_norm": f"item_{i}", "N4": f"Cat_{i}", "source": "llm_approved",
             "confidence": 0.80, "_similarity": 0.70 + i * 0.01}
            for i in range(10)
        ]]
        result = KBRetriever.select_enriched_examples(batch_results, max_examples=3)
        assert len(result) == 3

    def test_select_enriched_examples_n4_diversity(self):
        """select_enriched_examples limits entries per N4 to ensure diversity."""
        # 5 entries all with same N4
        batch_results = [[
            {"description_norm": f"item_{i}", "N4": "Same Category", "source": "llm_approved",
             "confidence": 0.80, "_similarity": 0.70 + i * 0.01}
            for i in range(5)
        ]]
        result = KBRetriever.select_enriched_examples(batch_results, max_examples=10)
        # Should be limited to 3 per N4
        assert len(result) == 3

    def test_select_enriched_examples_keeps_best_similarity(self):
        """When same entry appears in multiple items, keeps highest similarity."""
        batch_results = [
            [{"description_norm": "parafuso m8", "N4": "Parafuso", "source": "llm_approved",
              "confidence": 0.85, "_similarity": 0.40}],
            [{"description_norm": "parafuso m8", "N4": "Parafuso", "source": "llm_approved",
              "confidence": 0.85, "_similarity": 0.95}],
        ]
        result = KBRetriever.select_enriched_examples(batch_results, max_examples=10)
        assert len(result) == 1
        # The entry should exist (deduplicated)
        assert result[0]["description_norm"] == "parafuso m8"
