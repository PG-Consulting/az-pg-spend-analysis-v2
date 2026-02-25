"""Tests for src.hierarchy_validator — HierarchyLookup and validate_and_correct."""

import pytest

from src.hierarchy_validator import HierarchyLookup, validate_and_correct


# ============================================================
# Local fixture — extended hierarchy tailored for test scenarios
# ============================================================

@pytest.fixture
def test_hierarchy():
    """
    Hierarchy designed so that every test scenario below has known paths.

    Includes entries for:
    - exact match, case-insensitive match
    - level shift detection (N2 returned as N1)
    - partial fuzzy N3 and N4
    - single N4 in an N3 (auto-select)
    - N4 unique in hierarchy (reverse lookup)
    - N4 in multiple paths (scored reverse lookup)
    - N4 tied scores (reverse lookup rejected)
    """
    return [
        # --- Materiais ---
        {"N1": "Materiais", "N2": "Componentes Mecanicos", "N3": "Fixacao", "N4": "Parafusos"},
        {"N1": "Materiais", "N2": "Componentes Mecanicos", "N3": "Fixacao", "N4": "Porcas"},
        {"N1": "Materiais", "N2": "Componentes Mecanicos", "N3": "Vedacao", "N4": "Aneis O-Ring"},
        {"N1": "Materiais", "N2": "Componentes Mecanicos", "N3": "Vedacao", "N4": "Juntas Metalicas"},
        {"N1": "Materiais", "N2": "Componentes Eletricos", "N3": "Cabos e Condutores", "N4": "Cabos de Potencia"},
        {"N1": "Materiais", "N2": "Componentes Eletricos", "N3": "Cabos e Condutores", "N4": "Cabos de Instrumentacao"},
        {"N1": "Materiais", "N2": "Componentes Eletricos", "N3": "Conectores", "N4": "Conectores Circulares"},
        # --- Servicos ---
        {"N1": "Servicos", "N2": "Manutencao", "N3": "Manutencao Preventiva", "N4": "Inspecao Programada"},
        {"N1": "Servicos", "N2": "Manutencao", "N3": "Manutencao Preventiva", "N4": "Troca de Filtros"},
        {"N1": "Servicos", "N2": "Manutencao", "N3": "Manutencao Corretiva", "N4": "Reparo de Motor"},
        {"N1": "Servicos", "N2": "Manutencao", "N3": "Manutencao Corretiva", "N4": "Reparo de Bomba"},
        {"N1": "Servicos", "N2": "Engenharia", "N3": "Projetos", "N4": "Projeto Naval"},
        {"N1": "Servicos", "N2": "Engenharia", "N3": "Projetos", "N4": "Projeto Estrutural"},
        # --- Equipamentos ---
        {"N1": "Equipamentos", "N2": "Propulsao", "N3": "Motores Principais", "N4": "Motor Diesel Maritimo"},
        {"N1": "Equipamentos", "N2": "Propulsao", "N3": "Motores Principais", "N4": "Motor a Gas"},
        {"N1": "Equipamentos", "N2": "Propulsao", "N3": "Sistemas Auxiliares", "N4": "Bomba de Combustivel"},
        {"N1": "Equipamentos", "N2": "Propulsao", "N3": "Sistemas Auxiliares", "N4": "Trocador de Calor"},
        {"N1": "Equipamentos", "N2": "Navegacao", "N3": "Instrumentos", "N4": "Radar Maritimo"},
        {"N1": "Equipamentos", "N2": "Navegacao", "N3": "Instrumentos", "N4": "GPS Diferencial"},
        # --- Entry with single N4 in its N3 (for auto-select test) ---
        {"N1": "Materiais", "N2": "Componentes Mecanicos", "N3": "Lubrificacao", "N4": "Graxa Naval"},
        # --- Duplicate N4 across different branches (for tied-score test) ---
        {"N1": "Servicos", "N2": "Engenharia", "N3": "Consultoria", "N4": "Analise Tecnica"},
        {"N1": "Equipamentos", "N2": "Navegacao", "N3": "Consultoria", "N4": "Analise Tecnica"},
    ]


@pytest.fixture
def lookup(test_hierarchy):
    return HierarchyLookup(test_hierarchy)


# ============================================================
# HierarchyLookup — construction / data integrity
# ============================================================

class TestHierarchyLookup:
    def test_lookup_valid_paths(self, lookup):
        """valid_paths should contain lowercase tuples of all entries."""
        assert ("materiais", "componentes mecanicos", "fixacao", "parafusos") in lookup.valid_paths
        assert ("equipamentos", "propulsao", "motores principais", "motor diesel maritimo") in lookup.valid_paths

    def test_lookup_valid_n1s(self, lookup):
        assert "materiais" in lookup.valid_n1s
        assert "servicos" in lookup.valid_n1s
        assert "equipamentos" in lookup.valid_n1s
        assert len(lookup.valid_n1s) == 3

    def test_lookup_n4_to_paths(self, lookup):
        """Reverse lookup: N4 -> list of (N1, N2, N3)."""
        paths = lookup.n4_to_paths.get("parafusos")
        assert paths is not None
        assert ("materiais", "componentes mecanicos", "fixacao") in paths

    def test_lookup_canonical_case(self, lookup):
        """Canonical case preserves original casing from hierarchy."""
        assert lookup.get_canonical("materiais") == "Materiais"
        assert lookup.get_canonical("componentes mecanicos") == "Componentes Mecanicos"
        assert lookup.get_canonical("motor diesel maritimo") == "Motor Diesel Maritimo"

    def test_lookup_handles_dict_input(self):
        """HierarchyLookup should accept a dict (values are entries)."""
        hierarchy_dict = {
            "0": {"N1": "Alpha", "N2": "Beta", "N3": "Gamma", "N4": "Delta"},
            "1": {"N1": "Alpha", "N2": "Beta", "N3": "Gamma", "N4": "Epsilon"},
        }
        lk = HierarchyLookup(hierarchy_dict)
        assert ("alpha", "beta", "gamma", "delta") in lk.valid_paths
        assert ("alpha", "beta", "gamma", "epsilon") in lk.valid_paths

    def test_lookup_skips_entries_without_n4(self):
        """Entries with empty or missing N4 should be ignored."""
        hierarchy = [
            {"N1": "A", "N2": "B", "N3": "C", "N4": ""},
            {"N1": "A", "N2": "B", "N3": "C"},  # N4 missing
            {"N1": "X", "N2": "Y", "N3": "Z", "N4": "W"},
        ]
        lk = HierarchyLookup(hierarchy)
        assert len(lk.valid_paths) == 1
        assert ("x", "y", "z", "w") in lk.valid_paths


# ============================================================
# validate_and_correct — cascade strategies
# ============================================================

def _make_result(n1, n2, n3, n4, source="LLM (Batch)", status="Único"):
    """Helper: creates a classification result dict matching real pipeline output."""
    return {
        "N1": n1, "N2": n2, "N3": n3, "N4": n4,
        "status": status,
        "source": source,
    }


class TestValidateAndCorrect:
    # --- Step A: Exact match ---
    def test_exact_match(self, test_hierarchy):
        results = [_make_result("Materiais", "Componentes Mecanicos", "Fixacao", "Parafusos")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["exact_match"] == 1
        assert corrected[0]["N4"] == "Parafusos"

    def test_exact_match_case_insensitive(self, test_hierarchy):
        results = [_make_result("MATERIAIS", "COMPONENTES MECANICOS", "FIXACAO", "PARAFUSOS")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["exact_match"] == 1
        # Should be restored to canonical case
        assert corrected[0]["N1"] == "Materiais"
        assert corrected[0]["N4"] == "Parafusos"

    # --- Step B: Level shift detection ---
    def test_level_shift_detection(self, test_hierarchy):
        """LLM returned N2 as N1, N3 as N2, N4 as N3 — shift by +1 level."""
        # "Componentes Mecanicos" is an N2 but returned as N1
        # "Fixacao" as N2, "Parafusos" as N3, something arbitrary as N4
        results = [_make_result("Componentes Mecanicos", "Fixacao", "Parafusos", "anything")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["level_shift"] == 1
        assert corrected[0]["N1"] == "Materiais"
        assert corrected[0]["N2"] == "Componentes Mecanicos"
        assert corrected[0]["N3"] == "Fixacao"
        assert corrected[0]["N4"] == "Parafusos"

    # --- Step C: Partial fuzzy matching ---
    def test_partial_fuzzy_n3(self, test_hierarchy):
        """N1/N2 exact, N3 fuzzy match (e.g. typo)."""
        # "Fixacoa" is close enough to "Fixacao" via difflib
        results = [_make_result("Materiais", "Componentes Mecanicos", "Fixacoa", "Parafusos")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["partial_fuzzy"] == 1
        assert corrected[0]["N3"] == "Fixacao"

    def test_partial_fuzzy_n4(self, test_hierarchy):
        """N1/N2/N3 exact, N4 fuzzy match."""
        # "Parafusso" is close to "Parafusos"
        results = [_make_result("Materiais", "Componentes Mecanicos", "Fixacao", "Parafusso")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["partial_fuzzy"] == 1
        assert corrected[0]["N4"] == "Parafusos"

    def test_partial_fuzzy_single_n4(self, test_hierarchy):
        """Only 1 N4 in the N3 branch -> auto-select even without fuzzy match."""
        # "Lubrificacao" has only "Graxa Naval" as N4 — a completely wrong N4 should auto-select
        results = [_make_result("Materiais", "Componentes Mecanicos", "Lubrificacao", "Qualquer Coisa")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["partial_fuzzy"] == 1
        assert corrected[0]["N4"] == "Graxa Naval"

    # --- Step D: N4-based reverse lookup ---
    def test_n4_reverse_unique(self, test_hierarchy):
        """N4 is unique in the hierarchy -> reverse lookup succeeds."""
        # "GPS Diferencial" is unique — only under Equipamentos/Navegacao/Instrumentos
        results = [_make_result("Wrong", "Wrong", "Wrong", "GPS Diferencial")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["n4_reverse"] == 1
        assert corrected[0]["N1"] == "Equipamentos"
        assert corrected[0]["N2"] == "Navegacao"
        assert corrected[0]["N3"] == "Instrumentos"
        assert corrected[0]["N4"] == "GPS Diferencial"

    def test_n4_reverse_scored(self, test_hierarchy):
        """N4 in multiple paths — best score (N1 overlap) wins."""
        # "Analise Tecnica" exists under both Servicos/Engenharia/Consultoria
        # and Equipamentos/Navegacao/Consultoria. Provide matching N1="Servicos" to score higher.
        results = [_make_result("Servicos", "Wrong", "Wrong", "Analise Tecnica")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["n4_reverse"] == 1
        assert corrected[0]["N1"] == "Servicos"
        assert corrected[0]["N2"] == "Engenharia"

    def test_n4_reverse_tie_rejected(self, test_hierarchy):
        """Tied scores in reverse lookup -> no correction (falls through to no_match)."""
        # "Analise Tecnica" in two paths, provide N1 that matches neither → both score 0 → tie
        results = [_make_result("Inexistente", "Inexistente", "Inexistente", "Analise Tecnica")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        # Should fall to no_match since the tie cannot be broken and score is 0
        assert stats["no_match"] == 1
        assert corrected[0]["N1"] == "Não Identificado"

    # --- Step E: No match ---
    def test_no_match_zeroed(self, test_hierarchy):
        """Completely invalid path -> set to 'Não Identificado'."""
        results = [_make_result("XYZ", "ABC", "DEF", "GHI")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["no_match"] == 1
        assert corrected[0]["N1"] == u"N\u00e3o Identificado"
        assert corrected[0]["status"] == "Nenhum"

    # --- Skips ---
    def test_skips_non_llm_source(self, test_hierarchy):
        """Items with source not containing 'LLM' should be skipped."""
        results = [_make_result("Anything", "Anything", "Anything", "Anything", source="KB (Direct Match)")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["skipped"] == 1
        # Original values preserved
        assert corrected[0]["N1"] == "Anything"

    def test_skips_nao_identificado(self, test_hierarchy):
        """Items with N1='Não Identificado' should be skipped."""
        results = [_make_result(u"N\u00e3o Identificado", "", "", "", source="LLM (Batch)")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["skipped"] == 1

    # --- Stats ---
    def test_stats_counts(self, test_hierarchy):
        """Stats dict should have correct counts for mixed inputs."""
        results = [
            _make_result("Materiais", "Componentes Mecanicos", "Fixacao", "Parafusos"),  # exact
            _make_result("XYZ", "ABC", "DEF", "GHI"),  # no_match
            _make_result("X", "Y", "Z", "W", source="KB (Direct Match)"),  # skipped
        ]
        _, stats = validate_and_correct(results, test_hierarchy)
        assert stats["exact_match"] == 1
        assert stats["no_match"] == 1
        assert stats["skipped"] == 1

    # --- Edge cases ---
    def test_empty_hierarchy(self):
        """Empty hierarchy -> everything is skipped (no valid paths to match)."""
        results = [_make_result("A", "B", "C", "D")]
        corrected, stats = validate_and_correct(results, [])
        # With empty hierarchy, N1 "A" is not a valid N1 and no matches exist,
        # but the item is LLM-sourced and not "Não Identificado", so it goes to no_match
        assert stats["no_match"] == 1

    def test_empty_results(self):
        """Empty chunk_results should produce no errors and zero stats."""
        hierarchy = [{"N1": "A", "N2": "B", "N3": "C", "N4": "D"}]
        corrected, stats = validate_and_correct([], hierarchy)
        assert corrected == []
        assert all(v == 0 for v in stats.values())

    def test_fuzzy_cache_used(self, test_hierarchy):
        """Two items with the same fuzzy need should produce consistent results."""
        results = [
            _make_result("Materiais", "Componentes Mecanicos", "Fixacoa", "Parafusos"),
            _make_result("Materiais", "Componentes Mecanicos", "Fixacoa", "Porcas"),
        ]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        # Both should resolve "Fixacoa" -> "Fixacao" via fuzzy (and cache)
        assert corrected[0]["N3"] == "Fixacao"
        assert corrected[1]["N3"] == "Fixacao"

    def test_n4_fuzzy_global(self, test_hierarchy):
        """Fuzzy match N4 against all valid N4s (Step D with fuzzy N4)."""
        # "Radar Maritim" is close to "Radar Maritimo" (unique N4)
        results = [_make_result("Wrong", "Wrong", "Wrong", "Radar Maritim")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["n4_reverse"] == 1
        assert corrected[0]["N4"] == "Radar Maritimo"
        assert corrected[0]["N1"] == "Equipamentos"

    def test_pre_built_lookup(self, test_hierarchy, lookup):
        """Passing a pre-built HierarchyLookup should work identically."""
        results = [_make_result("Materiais", "Componentes Mecanicos", "Fixacao", "Parafusos")]
        corrected, stats = validate_and_correct(results, test_hierarchy, lookup=lookup)
        assert stats["exact_match"] == 1
        assert corrected[0]["N1"] == "Materiais"

    # --- Integration: real pipeline field name ---
    def test_reads_source_field_from_llm_pipeline(self, test_hierarchy):
        """Validate that results with 'source' field (from LLM pipeline) are processed."""
        # Simulates exact output from _llm_direct_pipeline in core_classification.py
        result = {
            "description": "Parafuso M10x50",
            "N1": "Wrong", "N2": "Wrong", "N3": "Wrong", "N4": "GPS Diferencial",
            "source": "LLM (Batch)",
            "confidence": 0.8,
        }
        corrected, stats = validate_and_correct([result], test_hierarchy)
        assert stats["skipped"] == 0, "LLM pipeline results must NOT be skipped"
        assert stats["n4_reverse"] == 1
        assert corrected[0]["N1"] == "Equipamentos"

    def test_n4_reverse_fixes_skipped_level(self, test_hierarchy):
        """LLM returned correct N4 but skipped intermediate level in path."""
        # Simulates: hierarchy has Materiais > Componentes Mecanicos > Fixacao > Parafusos
        # LLM returned: N1=Materiais, N2=Fixacao, N3=Parafusos, N4=Parafusos (skipped N2)
        results = [_make_result("Materiais", "Fixacao", "Parafusos", "Parafusos")]
        corrected, stats = validate_and_correct(results, test_hierarchy)
        assert stats["skipped"] == 0
        # N4 "Parafusos" is unique → n4_reverse should fix the path
        assert stats["n4_reverse"] == 1
        assert corrected[0]["N1"] == "Materiais"
        assert corrected[0]["N2"] == "Componentes Mecanicos"
        assert corrected[0]["N3"] == "Fixacao"
        assert corrected[0]["N4"] == "Parafusos"
