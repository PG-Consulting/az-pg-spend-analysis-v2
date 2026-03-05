"""Tests for src.taxonomy_engine — generate_summary vectorized and generate_analytics."""

import pandas as pd
import pytest

from src.taxonomy_engine import generate_summary, generate_analytics


class TestGenerateSummary:
    """Testes para generate_summary com contagem vetorizada."""

    def test_generate_summary_counts(self):
        """Itens com N1 vazio ou N2='Não Identificado' contam como 'nenhum'."""
        df = pd.DataFrame({
            "N1": ["Cat1", "Cat1", "", "Cat2"],
            "N2": ["Sub1", "Sub1", "Sub2", "Não Identificado"],
            "N3": ["A", "B", "C", "D"],
            "N4": ["X", "Y", "Z", "W"],
        })
        result = generate_summary(df, "Descricao")
        assert result["total_linhas"] == 4
        assert result["nenhum"] == 2  # empty N1 + "Não Identificado" N2
        assert result["unico"] == 2

    def test_generate_summary_all_classified(self):
        """Quando todos os itens estão classificados, nenhum deve ser 0."""
        df = pd.DataFrame({
            "N1": ["A", "B"],
            "N2": ["C", "D"],
            "N3": ["E", "F"],
            "N4": ["G", "H"],
        })
        result = generate_summary(df, "Descricao")
        assert result["nenhum"] == 0
        assert result["unico"] == 2

    def test_generate_summary_all_unclassified(self):
        """Todos os itens 'Não Identificado' → todos como nenhum."""
        df = pd.DataFrame({
            "N1": ["Não Identificado", "Não Identificado"],
            "N2": ["Não Identificado", "Não Identificado"],
            "N3": ["Não Identificado", "Não Identificado"],
            "N4": ["Não Identificado", "Não Identificado"],
        })
        result = generate_summary(df, "Descricao")
        assert result["nenhum"] == 2
        assert result["unico"] == 0

    def test_generate_summary_empty_df(self):
        """DataFrame vazio deve retornar zeros."""
        df = pd.DataFrame(columns=["N1", "N2", "N3", "N4"])
        result = generate_summary(df, "Descricao")
        assert result["total_linhas"] == 0
        assert result["nenhum"] == 0
        assert result["unico"] == 0

    def test_generate_summary_nan_values(self):
        """NaN/None deve ser tratado como vazio → conta como nenhum."""
        df = pd.DataFrame({
            "N1": ["Cat1", None],
            "N2": ["Sub1", "Sub2"],
            "N3": ["A", "B"],
            "N4": ["X", "Y"],
        })
        result = generate_summary(df, "Descricao")
        # Nota: a implementação original com row.get() convertia None→"None" (string),
        # que NÃO está em _incomplete. A versão vetorizada corrige esse bug tratando
        # NaN como vazio (incompleto). Teste alinhado com comportamento correto.
        assert result["nenhum"] == 1  # None N1 = incompleto
        assert result["unico"] == 1

    def test_generate_summary_whitespace_only(self):
        """Strings com apenas espaços devem contar como vazio → nenhum."""
        df = pd.DataFrame({
            "N1": ["Cat1", "  "],
            "N2": ["Sub1", "Sub2"],
            "N3": ["A", "B"],
            "N4": ["X", "Y"],
        })
        result = generate_summary(df, "Descricao")
        assert result["nenhum"] == 1
        assert result["unico"] == 1

    def test_generate_summary_preserves_schema(self):
        """Resultado deve conter todas as chaves esperadas."""
        df = pd.DataFrame({
            "N1": ["A"],
            "N2": ["B"],
            "N3": ["C"],
            "N4": ["D"],
        })
        result = generate_summary(df, "Descricao")
        assert "total_linhas" in result
        assert "coluna_descricao_utilizada" in result
        assert "unico" in result
        assert "ambiguo" in result
        assert "nenhum" in result
        assert result["ambiguo"] == 0

    def test_generate_summary_mixed_nao_identificado(self):
        """Apenas UM nível 'Não Identificado' já marca como nenhum."""
        df = pd.DataFrame({
            "N1": ["Cat1", "Cat2", "Cat3"],
            "N2": ["Sub1", "Não Identificado", "Sub3"],
            "N3": ["A", "B", "Não Identificado"],
            "N4": ["X", "Y", "Z"],
        })
        result = generate_summary(df, "Descricao")
        assert result["nenhum"] == 2  # linhas 1 e 2
        assert result["unico"] == 1

    def test_generate_summary_missing_columns(self):
        """Se colunas N1-N4 não existem no DataFrame, não deve falhar."""
        df = pd.DataFrame({
            "Descricao": ["item1", "item2"],
        })
        result = generate_summary(df, "Descricao")
        assert result["total_linhas"] == 2
        # Sem colunas N1-N4, a coluna não existe → não ativa mask → nenhum = 0
        assert result["nenhum"] == 0


# ---------------------------------------------------------------------------
# generate_analytics
# ---------------------------------------------------------------------------

class TestGenerateAnalytics:
    """Testes para generate_analytics — Pareto N1-N4 e campos de compatibilidade."""

    def test_pareto_n1_order(self):
        """Pareto N1 deve ordenar por contagem decrescente, com 'A' no topo."""
        df = pd.DataFrame({
            "N1": ["A"] * 80 + ["B"] * 15 + ["C"] * 5,
            "N2": ["Sub"] * 100,
            "N3": ["X"] * 100,
            "N4": ["Y"] * 100,
        })
        analytics = generate_analytics(df)
        assert "pareto_N1" in analytics
        assert len(analytics["pareto_N1"]) > 0
        assert analytics["pareto_N1"][0]["N1"] == "A"
        assert analytics["pareto_N1"][0]["Contagem"] == 80

    def test_pareto_classe_abc(self):
        """Pareto deve classificar como A (<=80%), B (<=95%), C (>95%).

        Usa 200 itens para evitar problemas de precisão float nos limites exatos.
        70% A (classe A), 20% B (classe B, cumsum=90%), 10% C (classe C, cumsum=100%).
        """
        df = pd.DataFrame({
            "N1": ["A"] * 140 + ["B"] * 40 + ["C"] * 20,
            "N2": ["Sub"] * 200,
            "N3": ["X"] * 200,
            "N4": ["Y"] * 200,
        })
        analytics = generate_analytics(df)
        pareto = analytics["pareto_N1"]
        # A: 70% do total → cumsum=0.70 → Classe A
        assert pareto[0]["Classe"] == "A"
        # B: 20% → cumsum=0.90 → Classe B
        assert pareto[1]["Classe"] == "B"
        # C: 10% → cumsum=1.0 → Classe C
        assert pareto[2]["Classe"] == "C"

    def test_pareto_all_levels(self):
        """Analytics deve conter pareto para N1, N2, N3 e N4."""
        df = pd.DataFrame({
            "N1": ["Cat1", "Cat1", "Cat2"],
            "N2": ["Sub1", "Sub2", "Sub1"],
            "N3": ["A", "B", "C"],
            "N4": ["X", "Y", "Z"],
        })
        analytics = generate_analytics(df)
        for level in ["N1", "N2", "N3", "N4"]:
            assert f"pareto_{level}" in analytics

    def test_pareto_legacy_alias(self):
        """'pareto' deve ser alias de 'pareto_N4' (backward compat)."""
        df = pd.DataFrame({
            "N1": ["Cat1"],
            "N2": ["Sub1"],
            "N3": ["A"],
            "N4": ["X"],
        })
        analytics = generate_analytics(df)
        assert analytics["pareto"] == analytics["pareto_N4"]

    def test_empty_df(self):
        """DataFrame vazio deve retornar listas vazias para todos os paretos."""
        df = pd.DataFrame(columns=["N1", "N2", "N3", "N4"])
        analytics = generate_analytics(df)
        assert "pareto_N1" in analytics
        assert analytics["pareto_N1"] == []
        assert analytics["pareto_N2"] == []
        assert analytics["pareto_N3"] == []
        assert analytics["pareto_N4"] == []

    def test_nao_identificado_excluded_from_pareto(self):
        """Itens 'Não Identificado' não devem aparecer no Pareto."""
        df = pd.DataFrame({
            "N1": ["Cat1", "Cat1", "Não Identificado"],
            "N2": ["Sub1", "Sub1", "Não Identificado"],
            "N3": ["A", "A", "Não Identificado"],
            "N4": ["X", "X", "Não Identificado"],
        })
        analytics = generate_analytics(df)
        n1_values = [r["N1"] for r in analytics["pareto_N1"]]
        assert "Não Identificado" not in n1_values
        # Somente Cat1 deve aparecer
        assert len(analytics["pareto_N1"]) == 1
        assert analytics["pareto_N1"][0]["Contagem"] == 2

    def test_empty_values_excluded_from_pareto(self):
        """Itens com N1 vazio não devem aparecer no Pareto."""
        df = pd.DataFrame({
            "N1": ["Cat1", ""],
            "N2": ["Sub1", "Sub1"],
            "N3": ["A", "B"],
            "N4": ["X", "Y"],
        })
        analytics = generate_analytics(df)
        assert len(analytics["pareto_N1"]) == 1
        assert analytics["pareto_N1"][0]["N1"] == "Cat1"

    def test_gaps_and_ambiguity_empty(self):
        """gaps e ambiguity devem retornar listas vazias (compat legado)."""
        df = pd.DataFrame({
            "N1": ["Cat1"],
            "N2": ["Sub1"],
            "N3": ["A"],
            "N4": ["X"],
        })
        analytics = generate_analytics(df)
        assert analytics["gaps"] == []
        assert analytics["ambiguity"] == []

    def test_missing_columns_handled(self):
        """Se colunas N1-N4 não existem, pareto deve retornar listas vazias."""
        df = pd.DataFrame({
            "Descricao": ["item1", "item2"],
        })
        analytics = generate_analytics(df)
        for level in ["N1", "N2", "N3", "N4"]:
            assert analytics[f"pareto_{level}"] == []

    def test_pareto_percentage_fields(self):
        """Cada entrada do Pareto deve ter % do Total e % Acumulado."""
        df = pd.DataFrame({
            "N1": ["A"] * 60 + ["B"] * 40,
            "N2": ["Sub"] * 100,
            "N3": ["X"] * 100,
            "N4": ["Y"] * 100,
        })
        analytics = generate_analytics(df)
        pareto = analytics["pareto_N1"]
        assert pareto[0]["% do Total"] == pytest.approx(0.6)
        assert pareto[0]["% Acumulado"] == pytest.approx(0.6)
        assert pareto[1]["% do Total"] == pytest.approx(0.4)
        assert pareto[1]["% Acumulado"] == pytest.approx(1.0)
