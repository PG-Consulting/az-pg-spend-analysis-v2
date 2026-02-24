"""Tests for src.preprocessing — normalize_text, normalize_corpus, build_tfidf_vectorizer."""

import pytest
from sklearn.feature_extraction.text import TfidfVectorizer

from src.preprocessing import normalize_text, normalize_corpus, build_tfidf_vectorizer


# ============================================================
# normalize_text — basic transformations
# ============================================================

class TestNormalizeText:
    def test_lowercase(self):
        assert normalize_text("PARAFUSO") == "parafuso"

    def test_accent_removal(self):
        result = normalize_text("manutenção")
        assert result == "manutencao"

    def test_noise_words_removed(self):
        # "de" is a noise word
        result = normalize_text("peça de motor")
        assert result == "peca motor"

    def test_multiple_noise_words(self):
        # "a", "da" are noise words
        result = normalize_text("a porca da válvula")
        assert result == "porca valvula"

    def test_abbreviation_expansion(self):
        # "etiq" -> "etiqueta" per ABBREVIATIONS dict
        result = normalize_text("etiq adesiva")
        assert result == "etiqueta adesiva"

    def test_punctuation_removal(self):
        result = normalize_text("motor/bomba")
        assert result == "motor bomba"

    def test_hyphen_becomes_space(self):
        result = normalize_text("válvula-solenoide")
        assert result == "valvula solenoide"

    def test_multiple_spaces_compacted(self):
        result = normalize_text("motor   bomba")
        assert result == "motor bomba"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_none_input(self):
        assert normalize_text(None) == ""

    def test_numeric_input(self):
        assert normalize_text(12345) == ""

    def test_mixed_case_and_accents(self):
        result = normalize_text("Serviço de Manutenção - OEM")
        assert result == "servico manutencao oem"

    def test_special_characters(self):
        result = normalize_text("item@#$%test")
        assert result == "item test"

    def test_preserve_numbers(self):
        # Numbers (and alphanumeric tokens like m8x120) should be kept
        result = normalize_text("parafuso m8x120")
        assert result == "parafuso m8x120"


# ============================================================
# normalize_corpus
# ============================================================

class TestNormalizeCorpus:
    def test_normalize_corpus(self):
        corpus = ["PARAFUSO M8", "Válvula de Controle", "etiq adesiva"]
        result = normalize_corpus(corpus)
        assert result == ["parafuso m8", "valvula controle", "etiqueta adesiva"]

    def test_normalize_corpus_empty(self):
        assert normalize_corpus([]) == []


# ============================================================
# build_tfidf_vectorizer
# ============================================================

class TestBuildTfidfVectorizer:
    def test_build_tfidf_vectorizer(self):
        vec = build_tfidf_vectorizer()
        assert isinstance(vec, TfidfVectorizer)

    def test_tfidf_vectorizer_params(self):
        vec = build_tfidf_vectorizer(max_features=3000, ngram_range=(1, 3))
        assert vec.max_features == 3000
        assert vec.ngram_range == (1, 3)
