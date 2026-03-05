"""Tests for src.taxonomy_engine — generate_summary vectorized."""

import pandas as pd
import pytest

from src.taxonomy_engine import generate_summary


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
