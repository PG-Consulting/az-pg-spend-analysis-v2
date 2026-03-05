"""
Shared preprocessing utilities for Spend Analysis Classification.

This module provides text normalization and feature extraction functions
used by both the training pipeline and the ML classifier runtime.
"""

import re
import unicodedata
from typing import List
from sklearn.feature_extraction.text import TfidfVectorizer


# ================================
# CONFIGURATION CONSTANTS
# ================================

# Common abbreviations found in procurement data
ABBREVIATIONS = {
    "etiq": "etiqueta",  # Label/tag abbreviation
}

# Noise words (prepositions, articles) removed during normalization
NOISE_WORDS = {
    "para", "com", "de", "do", "da",  # Prepositions
    "em", "no", "na",                  # More prepositions
    "a", "o", "as", "os",              # Articles
}


# ================================
# TEXT NORMALIZATION
# ================================

def normalize_text(s: str) -> str:
    """
    Normalize text for comparison.

    Performs the following operations:
      - Converts to lowercase.
      - Removes accents (using NFD normalization + Mn category filtering).
      - Removes punctuation (keeps letters, numbers, spaces, hyphens).
      - Replaces hyphens with spaces.
      - Expands abbreviations.
      - Removes noise words (articles, prepositions).
      - Compacts multiple spaces into one.

    Args:
        s (str): The input string.

    Returns:
        str: The normalized string.
    """
    if not isinstance(s, str):
        return ""
    
    s = s.lower()
    
    # Remove accents (NFD + Mn filter)
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    
    # Remove everything that is not a letter, number, space, or hyphen
    s = re.sub(r"[^\w\s\-]", " ", s, flags=re.UNICODE)
    
    # Hyphen becomes a separator (space)
    s = s.replace("-", " ")
    
    # Compact spaces
    s = re.sub(r"\s+", " ", s).strip()
    
    # Expand abbreviations and remove noise words
    words = s.split()
    new_words = []
    for w in words:
        # Expand abbreviation if exists
        w = ABBREVIATIONS.get(w, w)
        
        # Skip noise words
        if w in NOISE_WORDS:
            continue
            
        new_words.append(w)
    
    s = " ".join(new_words)
    
    return s


def normalize_corpus(texts: List[str]) -> List[str]:
    """
    Normalize a corpus of texts.

    Args:
        texts: List of text strings to normalize.

    Returns:
        List of normalized text strings.
    """
    return [normalize_text(text) for text in texts]


# ================================
# FEATURE EXTRACTION
# ================================

def build_tfidf_vectorizer(
    max_features: int = 5000,
    ngram_range: tuple = (1, 2),
    min_df: int = 2,
    max_df: float = 0.95
) -> TfidfVectorizer:
    """
    Create a TF-IDF vectorizer configured for spend classification.

    Args:
        max_features: Maximum number of features (vocabulary size).
        ngram_range: Range of n-grams to extract (unigrams and bigrams by default).
        min_df: Minimum document frequency (ignore terms appearing in fewer documents).
        max_df: Maximum document frequency (ignore terms appearing in more than this fraction).

    Returns:
        Configured TfidfVectorizer instance.
    """
    return TfidfVectorizer(
        max_features=max_features,
        ngram_range=ngram_range,
        min_df=min_df,
        max_df=max_df,
        lowercase=False,  # Already handled by normalize_text
        strip_accents=None,  # Already handled by normalize_text
        token_pattern=r"(?u)\b\w+\b",  # Word tokens
    )


# ================================
# HEADER NORMALIZATION
# ================================

def normalize_header(header: str) -> str:
    """
    Normaliza nomes de colunas de arquivos de treinamento para nomes canônicos.

    Mapeia variações comuns (com/sem acento, inglês/português) para os nomes
    esperados pelo pipeline: Descricao, N1, N2, N3, N4.

    Args:
        header: Nome original da coluna.

    Returns:
        Nome canônico da coluna ou o header original se não houver mapeamento.
    """
    normalized = unicodedata.normalize("NFD", str(header)).encode("ascii", "ignore").decode("utf-8").lower().strip()
    if normalized in ("descricao", "item_description", "description", "desc"):
        return "Descricao"
    if normalized in ("n1", "nivel 1", "level 1", "categoria"):
        return "N1"
    if normalized in ("n2", "nivel 2", "level 2", "subcategoria1"):
        return "N2"
    if normalized in ("n3", "nivel 3", "level 3", "subcategoria2"):
        return "N3"
    if normalized in ("n4", "nivel 4", "level 4", "subcategoria"):
        return "N4"
    return header
