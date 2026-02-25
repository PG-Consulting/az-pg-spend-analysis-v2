"""
Core logic for Spend Analysis Classification (N4 x Keyword).

This module contains the logic to normalize text, build regex patterns from a dictionary,
and classify item descriptions into N4 subcategories based on keyword matching.
"""

import re
from collections import Counter
from functools import lru_cache
from typing import List, Dict, Any, Tuple

import pandas as pd

from src.preprocessing import normalize_text

# ================================
# CONFIGURATION CONSTANTS
# ================================

# Default candidates for the description column name.
# Tries these names in order when auto-detecting the description column.
# Supports both Portuguese (with/without accents) and English names.
COL_DESC_CANDIDATES_DEFAULT = [
    "Item_Description",  # Standard English name
    "Descricao",         # Portuguese without accent
    "Descrição",         # Portuguese with accent
    "Descrição do Item", # Full Portuguese name
    "Material_Description",
    "Description",
    "Long_Description",
    "Short_Description",
    "Texto Breve",
    "Texto Longo"
]

# Analytics configuration
PARETO_CLASS_A_THRESHOLD = 0.80  # 80% threshold for Pareto Class A
PARETO_CLASS_B_THRESHOLD = 0.95  # 95% threshold for Pareto Class B
MIN_WORD_LENGTH_FOR_GAPS = 3     # Minimum word length for gap analysis
LRU_CACHE_SIZE = 10000           # Maximum cache size for duplicate descriptions
TOP_GAPS_COUNT = 20              # Number of top gap words to return
TOP_AMBIGUITY_COUNT = 20         # Number of top ambiguous combinations to return


# ================================
# HELPERS
# ================================

def split_terms(cell_value: Any) -> List[str]:
    """
    Split a comma-separated string into a list of terms.

    Handles:
      - None or NaN values (returns empty list).
      - Existing lists (returns as is).
      - Extra spaces around terms.
      - Empty terms (removes them).

    Args:
        cell_value: The input cell value (str, list, float/NaN, or None).

    Returns:
        List[str]: A list of cleaned terms.
    """
    if cell_value is None:
        return []
    
    if isinstance(cell_value, float) and pd.isna(cell_value):
        return []
    
    if isinstance(cell_value, list):
        terms = cell_value
    else:
        terms = [t.strip() for t in str(cell_value).split(",")]
    
    return [t for t in terms if t]


def to_regex(term: str) -> re.Pattern:
    r"""
    Generate a regex pattern for a whole word/phrase, normalized.

    Tolerates flexible separators (spaces, hyphens, underscores) in the input text.
    Example: 'brown sugar' -> r'\bbrown[\s_-]+sugar\b'

    Args:
        term (str): The term to convert to regex.

    Returns:
        re.Pattern: The compiled regex pattern.
    """
    norm = normalize_text(term)
    if not norm:
        norm = term.lower()
    
    norm = re.escape(norm)
    # Spaces in the expression become flexible separators (space/hyphen/underscore)
    norm = norm.replace(r"\ ", r"[\s_-]+")
    
    return re.compile(rf"\b{norm}\b", flags=re.IGNORECASE)


def pick(df: pd.DataFrame, options: List[str]) -> str:
    """
    Select the first existing column in the DataFrame from a list of options.

    Tries exact match first, then case/accent-insensitive match.

    Args:
        df (pd.DataFrame): The DataFrame to search.
        options (List[str]): List of column name options.

    Returns:
        str: The name of the found column.

    Raises:
        ValueError: If none of the options are found in the DataFrame.
    """
    for option in options:
        if option in df.columns:
            return option
    
    normalized_cols = {normalize_text(c): c for c in df.columns}
    for option in options:
        key = normalize_text(option)
        if key in normalized_cols:
            return normalized_cols[key]
    
    raise ValueError(
        f"Column not found. Try renaming to one of these: {options}"
    )


# ================================
# CORE: LOAD AND BUILD PATTERNS
# ================================

def build_patterns(
    dict_df: pd.DataFrame,
) -> Tuple[Dict[str, List[re.Pattern]], Dict[str, List[str]], Dict[str, Dict[str, str]]]:
    """
    Build regex patterns from the dictionary DataFrame.

    Constructs:
      - patterns_by_n4: Mapping of N4 category -> list of regex patterns.
      - terms_by_n4:    Mapping of N4 category -> list of original terms (for reporting matches).
      - taxonomy_by_n4: Mapping of N4 category -> dict with N1, N2, N3, N4 values.

    Supports:
      - Base keyword column.
      - Optional variations column.
      - Stopword filtering.
      - Normalized deduplication.

    Args:
        dict_df (pd.DataFrame): The dictionary DataFrame.

    Returns:
        Tuple containing patterns_by_n4, terms_by_n4, and taxonomy_by_n4.
    """
    # Tolerance for dictionary column names
    COL_N1 = pick(dict_df, ["N1_Categoria", "N1", "Categoria N1"])
    COL_N2 = pick(dict_df, ["N2_Subcategoria", "N2", "Subcategoria N2"])
    COL_N3 = pick(dict_df, ["N3_Subcategoria", "N3", "Subcategoria N3"])
    COL_N4 = pick(dict_df, ["N4_Subcategorias", "N4_Subcategoria", "N4", "Subcategoria N4"])
    COL_BASE = pick(
        dict_df,
        [
            "Palavras_chave",
            "Palavras-chave",
            "Keywords",
            "Palavra_Chave",
            "Palavras-chave / Variações",
        ],
    )
    
    try:
        COL_VAR = pick(
            dict_df,
            [
                "Variacoes",
                "Variações",
                "Variacoes_Palavras",
                "Variacoes Palavras",
                "Variations",
            ],
        )
    except ValueError:
        COL_VAR = None
    
    # Optional stopwords (prevent overly generic terms from matching alone)
    STOP = {
        "kit",
        "conjunto",
        "peca",
        "pecas",
        "peça",
        "peças",
        "servico",
        "servicos",
        "serviço",
        "serviços",
        "varios",
        "diversos",
    }
    
    patterns_by_n4: Dict[str, List[re.Pattern]] = {}
    terms_by_n4: Dict[str, List[str]] = {}
    taxonomy_by_n4: Dict[str, Dict[str, str]] = {}
    
    for _, row in dict_df.iterrows():
        n1_value = str(row.get(COL_N1, "")).strip()
        n2_value = str(row.get(COL_N2, "")).strip()
        n3_value = str(row.get(COL_N3, "")).strip()
        n4_category = str(row.get(COL_N4, "")).strip()
        
        if not n4_category:
            continue
        
        base_terms = split_terms(row.get(COL_BASE, ""))
        variation_terms = split_terms(row.get(COL_VAR, "")) if COL_VAR else []
        all_terms = base_terms + variation_terms
        
        # Remove empty and duplicate (normalized) terms + apply stopwords
        seen_normalized = set()
        clean_terms = []
        for term in all_terms:
            normalized_key = normalize_text(term)
            if (not normalized_key) or (normalized_key in seen_normalized) or (normalized_key in STOP):
                continue
            seen_normalized.add(normalized_key)
            clean_terms.append(term)
        
        patterns = [to_regex(term) for term in clean_terms]
        
        # Always populate taxonomy for this N4 (use first occurrence found)
        if n4_category not in taxonomy_by_n4:
            taxonomy_by_n4[n4_category] = {
                "N1": n1_value,
                "N2": n2_value,
                "N3": n3_value,
                "N4": n4_category
            }

        if not patterns:
            continue
        
        # Merge with existing patterns for this N4 if it appeared before
        if n4_category in patterns_by_n4:
            patterns_by_n4[n4_category].extend(patterns)
            terms_by_n4[n4_category].extend(clean_terms)
        else:
            patterns_by_n4[n4_category] = patterns
            terms_by_n4[n4_category] = clean_terms
    
    # Do NOT raise error if dictionary has no keywords (allows ML-only usage)
    # if not patterns_by_n4:
    #     raise ValueError(...)
    if not patterns_by_n4:
        # Just return empty structures if no keywords found
        pass
    
    return patterns_by_n4, terms_by_n4, taxonomy_by_n4


# ================================
# DESCRIPTION MATCHING WITH PATTERNS
# ================================

def match_n4_without_priority(
    desc_norm: str,
    patterns_by_n4: Dict[str, List[re.Pattern]],
    terms_by_n4: Dict[str, List[str]],
    taxonomy_by_n4: Dict[str, Dict[str, str]],
) -> Tuple[Dict[str, str], str, List[str], int]:
    """
    Match a normalized description against N4 patterns.

    Args:
        desc_norm (str): The normalized item description.
        patterns_by_n4 (Dict[str, List[re.Pattern]]): Regex patterns by N4.
        terms_by_n4 (Dict[str, List[str]]): Original terms by N4.
        taxonomy_by_n4 (Dict[str, Dict[str, str]]): Full taxonomy (N1-N4) by N4.

    Returns:
        Tuple:
          - taxonomy (Dict[str, str]): Dict with N1, N2, N3, N4 keys (empty dict if no match).
          - match_type (str): 'Único', 'Ambíguo', or 'Nenhum'.
          - matched_terms (List[str]): List of terms that matched from the winning N4(s).
          - match_score (int): The score of the winning N4(s).
    """
    if not desc_norm:
        return {}, "Nenhum", [], 0
    
    scores: Dict[str, int] = {}
    matched_terms_per_n4: Dict[str, List[str]] = {}
    
    for n4_category, pattern_list in patterns_by_n4.items():
        score = 0
        matched_terms = []
        
        for pattern, original_term in zip(pattern_list, terms_by_n4[n4_category]):
            if pattern.search(desc_norm):
                score += 1
                matched_terms.append(original_term)
        
        if score > 0:
            scores[n4_category] = score
            matched_terms_per_n4[n4_category] = matched_terms
    
    if not scores:
        return {}, "Nenhum", [], 0
    
    # Find highest score
    max_score = max(scores.values())
    winners = [n4 for n4, score in scores.items() if score == max_score]
    
    if len(winners) == 1:
        winning_n4 = winners[0]
        return (
            taxonomy_by_n4.get(winning_n4, {}),
            "Único",
            matched_terms_per_n4.get(winning_n4, []),
            max_score,
        )
    else:
        # Tie -> Ambiguous - check each level independently
        # Only show ambiguity at levels where values actually differ
        
        # Extract values for each level across all winners
        n1_values = [taxonomy_by_n4.get(n4, {}).get("N1", "") for n4 in winners]
        n2_values = [taxonomy_by_n4.get(n4, {}).get("N2", "") for n4 in winners]
        n3_values = [taxonomy_by_n4.get(n4, {}).get("N3", "") for n4 in winners]
        n4_values = winners
        
        # For each level, check if all values are the same
        # If yes, use the single value; if no, join with " | "
        def resolve_level(values: List[str]) -> str:
            unique_values = list(dict.fromkeys(v for v in values if v))  # Remove duplicates, preserve order
            if len(unique_values) == 1:
                return unique_values[0]
            elif len(unique_values) > 1:
                return " | ".join(unique_values)
            else:
                return ""
        
        # Create a taxonomy dict with ambiguous markers only where needed
        ambiguous_taxonomy = {
            "N1": resolve_level(n1_values),
            "N2": resolve_level(n2_values),
            "N3": resolve_level(n3_values),
            "N4": resolve_level(n4_values)
        }
        
        # Join terms from tied categories (for reference)
        all_matched_terms: List[str] = []
        for winner_n4 in winners:
            all_matched_terms.extend(matched_terms_per_n4.get(winner_n4, []))
        
        # Deduplicate preserving order
        seen_normalized_terms = set()
        unique_matched_terms: List[str] = []
        for term in all_matched_terms:
            normalized_key = normalize_text(term)
            if normalized_key not in seen_normalized_terms:
                seen_normalized_terms.add(normalized_key)
                unique_matched_terms.append(term)
        
        return (ambiguous_taxonomy, "Ambíguo", unique_matched_terms, max_score)


# ================================
# MAIN FUNCTION FOR THE APP
# ================================

def classify_items(
    dict_records: List[Dict[str, Any]],
    item_records: List[Dict[str, Any]],
    desc_column: str = None,
    col_desc_candidates: List[str] = None,
) -> Dict[str, Any]:
    """
    Classify a list of items based on a dictionary of keywords.

    Args:
        dict_records (List[Dict[str, Any]]): List of dictionary records (N4 data).
        item_records (List[Dict[str, Any]]): List of item records to classify.
        desc_column (str, optional): Name of the column to use as description.
                                     If provided, it takes precedence.
        col_desc_candidates (List[str], optional): List of candidate column names for description.

    Returns:
        Dict[str, Any]: A dictionary containing:
          - "items": List of items with classification columns appended.
          - "summary": Summary dictionary with counts and general info.
    """
    if col_desc_candidates is None:
        col_desc_candidates = COL_DESC_CANDIDATES_DEFAULT.copy()
    
    if desc_column:
        # If caller explicitly provided a column, prioritize it
        col_desc_candidates = [desc_column] + [
            c for c in col_desc_candidates if c != desc_column
        ]
    
    dict_df = pd.DataFrame(dict_records)
    items_df = pd.DataFrame(item_records)
    
    # Identify description column in items file
    desc_col_name = pick(items_df, col_desc_candidates)
    
    # Normalize item description (keep original too)
    items_df["_desc_original"] = items_df[desc_col_name].fillna("")
    items_df["_desc_norm"] = items_df["_desc_original"].map(normalize_text)
    
    # Prepare dictionary N4 -> patterns
    patterns_by_n4, terms_by_n4, taxonomy_by_n4 = build_patterns(dict_df)
    
    # Apply classification with caching for duplicate descriptions
    # Convert patterns to hashable format for caching
    @lru_cache(maxsize=LRU_CACHE_SIZE)
    def classify_cached(desc_norm: str) -> Tuple[str, str, str, str, str, str, int, bool]:
        """Cached classification to avoid reprocessing duplicate descriptions."""
        taxonomy, match_type, matched_terms, match_score = match_n4_without_priority(
            desc_norm, patterns_by_n4, terms_by_n4, taxonomy_by_n4
        )
        
        # Extract individual levels from taxonomy dict
        n1 = taxonomy.get("N1", "")
        n2 = taxonomy.get("N2", "")
        n3 = taxonomy.get("N3", "")
        n4 = taxonomy.get("N4", "")
        
        matched_terms_str = ", ".join(matched_terms)
        needs_review = match_type in ("Ambíguo", "Nenhum")
        return n1, n2, n3, n4, match_type, matched_terms_str, match_score, needs_review
    
    # Vectorized application using pandas apply
    results = items_df["_desc_norm"].apply(classify_cached)
    
    # Unpack results into separate columns
    result_cols = {
        "N1": [r[0] for r in results],
        "N2": [r[1] for r in results],
        "N3": [r[2] for r in results],
        "N4": [r[3] for r in results],
        "Match_Type": [r[4] for r in results],
        "Matched_Terms": [r[5] for r in results],
        "Match_Score": [r[6] for r in results],
        "Needs_Review": [r[7] for r in results],
        "Classification_Source": ["Dictionary"] * len(results),
    }
    
    # Append result columns
    items_df = pd.concat([items_df, pd.DataFrame(result_cols)], axis=1)
    
    # Build summary
    total_items = len(items_df)
    ambiguous_count = int((items_df["Match_Type"] == "Ambíguo").sum())
    unmatched_count = int((items_df["Match_Type"] == "Nenhum").sum())
    unique_count = int((items_df["Match_Type"] == "Único").sum())
    
    summary = {
        "total_linhas": total_items,
        "coluna_descricao_utilizada": desc_col_name,
        "unico": unique_count,
        "ambiguo": ambiguous_count,
        "nenhum": unmatched_count,
    }
    
    # Generate analytics before dropping internal columns
    analytics = generate_analytics(items_df)

    # We don't need to return _desc_norm
    items_output = items_df.drop(columns=["_desc_norm"]).to_dict(orient="records")
    
    return {
        "items": items_output,
        "summary": summary,
        "analytics": analytics,
    }


def generate_analytics(df_items: pd.DataFrame) -> Dict[str, Any]:
    """
    Generate analytics from the classified items DataFrame.

    Calculates:
      1. Pareto (N4 volume) — the only analytics with real value.

    Gaps and ambiguity sections return empty lists for schema compatibility
    (these concepts only applied to the legacy dictionary path).

    Args:
        df_items (pd.DataFrame): The DataFrame with classification results.

    Returns:
        Dict[str, Any]: Dictionary containing lists of records for each analytic.
    """
    analytics = {}

    # 1. Pareto (Volume by Level)
    for level in ["N1", "N2", "N3", "N4"]:
        if level not in df_items.columns:
            analytics[f"pareto_{level}"] = []
            continue

        # Filter out empty, None, and "Não Identificado" (unclassified placeholder)
        df_valid = df_items[
            df_items[level].notna() &
            (df_items[level] != "") &
            (df_items[level] != "Não Identificado")
        ]

        if not df_valid.empty:
            # Count frequency
            pareto = df_valid[level].value_counts().reset_index()
            pareto.columns = [level, "Contagem"]

            total = pareto["Contagem"].sum()
            pareto["% do Total"] = pareto["Contagem"] / total
            pareto["% Acumulado"] = pareto["% do Total"].cumsum()

            # Mark Pareto classes
            pareto["Classe"] = pareto["% Acumulado"].apply(
                lambda x: "A" if x <= PARETO_CLASS_A_THRESHOLD
                else ("B" if x <= PARETO_CLASS_B_THRESHOLD else "C")
            )

            analytics[f"pareto_{level}"] = pareto.head(20).to_dict(orient="records")
        else:
            analytics[f"pareto_{level}"] = []

    # Preserve legacy 'pareto' key for backward compatibility (aliased to N4)
    analytics["pareto"] = analytics.get("pareto_N4", [])

    # Empty lists for schema compatibility (concepts from legacy dictionary path)
    analytics["gaps"] = []
    analytics["ambiguity"] = []

    return analytics

def generate_summary(df_items: pd.DataFrame, desc_col_name: str = "Descricao") -> Dict[str, Any]:
    """
    Generate summary statistics from the classified items DataFrame.

    Derives "classificado vs não classificado" from N1-N4 values instead of
    relying on the legacy Match_Type/status field.
    """
    total_items = len(df_items)

    # "Não classificado" = any N-level is empty or "Não Identificado"
    _incomplete = {"", "Não Identificado", "Nao Identificado"}
    nenhum_count = int(df_items.apply(
        lambda row: any(str(row.get(lvl, "")).strip() in _incomplete for lvl in ("N1", "N2", "N3", "N4")),
        axis=1
    ).sum())
    unico_count = total_items - nenhum_count

    return {
        "total_linhas": total_items,
        "coluna_descricao_utilizada": desc_col_name,
        "unico": unico_count,
        "ambiguo": 0,          # conceito removido — manter campo por compat
        "nenhum": nenhum_count,
    }