"""
Hybrid Classification: ML + Dictionary Fallback + Disambiguation

This module orchestrates the classification logic:
1. Try ML classifier first
2. If high confidence (>=0.45): "Único" (ML)
3. If medium confidence (0.25-0.44): Try Dictionary to disambiguate
   - If Dictionary = "Único": Use Dictionary result
   - Else: "Ambíguo" with hierarchical level detection
4. If low confidence (<0.25): Dictionary fallback
5. Return complete taxonomy (N1, N2, N3, N4) + matched terms + ambiguity info
"""

import logging
from typing import Dict, List, Tuple, Optional

from src.ml_classifier import predict_single, load_model
from src.taxonomy_engine import match_n4_without_priority
from src.llm_classifier import classify_items_with_llm
from src.utils import INCOMPLETE_VALUES


def find_ambiguity_level(candidates: List[Dict]) -> Tuple[Optional[str], List[str]]:
    """
    Find the first hierarchical level where candidates diverge.

    Args:
        candidates: List of candidate dicts with N1, N2, N3, N4 keys.

    Returns:
        Tuple of (ambiguity_level, unique_options_at_that_level)
        - ambiguity_level: "N1", "N2", "N3", "N4", or None if all same
        - unique_options: List of unique values at that level
    """
    if not candidates or len(candidates) < 2:
        return (None, [])

    for level in ["N1", "N2", "N3", "N4"]:
        values = list(set(c.get(level, "") for c in candidates if c.get(level)))
        if len(values) > 1:
            return (level, values)

    return (None, [])


class ClassificationResult:
    """
    Result of hybrid classification.
    """

    def __init__(
        self,
        status: str,  # "Único", "Ambíguo", "Nenhum"
        n4: str,
        n3: str,
        n2: str,
        n1: str,
        matched_terms: List[str],
        confidence: float,
        source: str,  # "ML" or "Dictionary" or "None"
        ambiguous_n4s: Optional[List[str]] = None,
        ambiguity_level: Optional[str] = None,  # "N1", "N2", "N3", "N4"
        ambiguous_options: Optional[List[str]] = None,  # Options at ambiguous level
        top_candidates: Optional[
            List[Dict]
        ] = None,  # ML top candidates for hierarchy remapping
    ):
        self.status = status
        self.n4 = n4
        self.n3 = n3
        self.n2 = n2
        self.n1 = n1
        self.matched_terms = matched_terms
        self.confidence = confidence
        self.source = source
        self.ambiguous_n4s = ambiguous_n4s or []
        self.ambiguity_level = ambiguity_level
        self.ambiguous_options = ambiguous_options or []
        self.top_candidates = top_candidates or []

    def to_dict(self) -> Dict:
        """Convert to dictionary format."""
        return {
            "status": self.status,
            "N1": self.n1,
            "N2": self.n2,
            "N3": self.n3,
            "N4": self.n4,
            "matched_terms": self.matched_terms,
            "ml_confidence": self.confidence,
            "classification_source": self.source,
            "ambiguous_n4s": self.ambiguous_n4s,
            "ambiguity_level": self.ambiguity_level,
            "ambiguous_options": self.ambiguous_options,
            "top_candidates": self.top_candidates,
        }


def classify_hybrid(
    description: str,
    sector: str,
    dict_patterns,
    dict_terms,
    dict_taxonomy,
    desc_norm: str = None,
    vectorizer=None,
    classifier=None,
    label_encoder=None,
    hierarchy=None,
    confidence_threshold_unique: float = 0.45,
    confidence_threshold_ambiguous: float = 0.25,
    use_llm_fallback: bool = False,
    client_context: str = "",
) -> ClassificationResult:
    """
    Classify an item using hybrid ML + dictionary approach with disambiguation.

    Decision logic:
    1. Try ML classifier first
    2. If confidence >= 0.45 -> "Único" (ML prediction)
    3. If confidence 0.25-0.44 -> Try Dictionary to disambiguate
       - If Dictionary = "Único" -> Use Dictionary result
       - Else -> "Ambíguo" with hierarchical level detection
    4. If confidence < 0.25 -> Try dictionary fallback
       - If dictionary matches -> Use dictionary result
       - If no match -> "Nenhum" (Não Classificado)

    Args:
        description: Item description (raw).
        sector: Sector name for ML model selection.
        dict_patterns: Dictionary regex patterns (from taxonomy_engine).
        dict_terms: Dictionary terms (from taxonomy_engine).
        dict_taxonomy: Dictionary taxonomy mapping (from taxonomy_engine).
        desc_norm: Pre-normalized description (optional, will normalize if None).
        vectorizer: ML vectorizer (loaded if None).
        classifier: ML classifier (loaded if None).
        label_encoder: ML label encoder (loaded if None).
        hierarchy: N4 hierarchy mapping (loaded if None).
        confidence_threshold_unique: Minimum confidence for "Único" via ML.
        confidence_threshold_ambiguous: Minimum confidence for "Ambíguo" via ML.

    Returns:
        ClassificationResult object.
    """
    # Decision 0: If sector is Padrão, defer to batch LLM (second pass in core_classification)
    # When use_llm_fallback=False (first pass), return "Nenhum" so the item is collected
    # for efficient parallel batch LLM processing instead of calling LLM per-row.
    if sector == "Padrão":
        if not use_llm_fallback:
            return ClassificationResult(
                status="Nenhum",
                n4="",
                n3="",
                n2="",
                n1="",
                matched_terms=[],
                confidence=0.0,
                source="Deferred to Batch LLM",
            )
        # Direct LLM call (only when use_llm_fallback=True, i.e. not in batch mode)
        llm_results, _ = classify_items_with_llm(
            [description],
            sector=sector,
            client_context=client_context,
            custom_hierarchy=hierarchy,
        )
        if llm_results:
            llm_res = llm_results[0]
            if llm_res.get("N1") and llm_res.get("N1") not in INCOMPLETE_VALUES:
                return ClassificationResult(
                    status="Único",
                    n4=llm_res.get("N4", ""),
                    n3=llm_res.get("N3", ""),
                    n2=llm_res.get("N2", ""),
                    n1=llm_res.get("N1", ""),
                    matched_terms=[],
                    confidence=llm_res.get("confidence", 0.0),
                    source="LLM (UNSPSC)",
                    ambiguous_n4s=[],
                )
    # Load ML models if not provided (only if sector is not "Padrão" or if we want to try ML anyway)
    # If standard, we might skip ML or use a generic one. For now, let's assume we try ML first if possible
    # but if sector is Padrão we might not have a model.
    if sector != "Padrão" and any(
        x is None for x in [vectorizer, classifier, label_encoder, hierarchy]
    ):
        try:
            vectorizer, classifier, label_encoder, hierarchy = load_model(sector=sector)
        except Exception:
            logging.warning(
                f"Could not load ML model for sector '{sector}'. Proceeding without ML."
            )
            vectorizer, classifier, label_encoder, hierarchy = None, None, None, None

    # Get ML prediction if model is loaded
    ml_confidence = 0.0
    ml_n4 = ""
    ml_n1 = ""
    ml_n2 = ""
    ml_n3 = ""
    top_candidates = []

    if classifier:
        ml_result = predict_single(
            description,
            sector=sector,
            vectorizer=vectorizer,
            classifier=classifier,
            label_encoder=label_encoder,
            hierarchy=hierarchy,
            top_k=3,
        )

        ml_confidence = ml_result["confidence"]
        ml_n4 = ml_result["n4_predicted"]
        ml_n1 = ml_result["N1"]
        ml_n2 = ml_result["N2"]
        ml_n3 = ml_result["N3"]
        top_candidates = ml_result["top_candidates"][:3]

    # Decision 1: High confidence -> Único (ML)
    if ml_confidence >= confidence_threshold_unique:
        return ClassificationResult(
            status="Único",
            n4=ml_n4,
            n3=ml_n3,
            n2=ml_n2,
            n1=ml_n1,
            matched_terms=[],
            confidence=ml_confidence,
            source="ML",
            top_candidates=top_candidates,
        )

    # Decision 2: Medium confidence -> Ambíguo (ML)
    # Note: We do NOT try Dictionary here - it was causing incorrect overrides
    if ml_confidence >= confidence_threshold_ambiguous:
        # Detect hierarchical ambiguity level
        ambiguity_level, ambiguous_options = find_ambiguity_level(top_candidates)
        ambiguous_n4s = [cand["N4"] for cand in top_candidates]

        # Determine what to fill based on ambiguity level
        # If N1 diverges: all blank
        # If N2 diverges: N1 filled, rest blank
        # If N3 diverges: N1, N2 filled, rest blank
        # If N4 diverges: N1, N2, N3 filled, N4 blank
        if ambiguity_level == "N1":
            n1, n2, n3, n4 = "", "", "", ""
        elif ambiguity_level == "N2":
            n1 = top_candidates[0].get("N1", "") if top_candidates else ""
            n2, n3, n4 = "", "", ""
        elif ambiguity_level == "N3":
            n1 = top_candidates[0].get("N1", "") if top_candidates else ""
            n2 = top_candidates[0].get("N2", "") if top_candidates else ""
            n3, n4 = "", ""
        elif ambiguity_level == "N4":
            n1 = top_candidates[0].get("N1", "") if top_candidates else ""
            n2 = top_candidates[0].get("N2", "") if top_candidates else ""
            n3 = top_candidates[0].get("N3", "") if top_candidates else ""
            n4 = ""
        else:
            # No divergence detected (shouldn't happen but fallback)
            n1, n2, n3, n4 = ml_n1, ml_n2, ml_n3, ml_n4

        return ClassificationResult(
            status="Ambíguo",
            n4=n4,
            n3=n3,
            n2=n2,
            n1=n1,
            matched_terms=[],
            confidence=ml_confidence,
            source="ML",
            ambiguous_n4s=ambiguous_n4s,
            ambiguity_level=ambiguity_level,
            ambiguous_options=ambiguous_options,
            top_candidates=top_candidates,
        )

    # Decision 3: Low confidence -> Try Dictionary fallback (only if provided)
    if (
        dict_patterns is not None
        and dict_terms is not None
        and dict_taxonomy is not None
    ):
        taxonomy, status, matched, score = match_n4_without_priority(
            desc_norm if desc_norm else description,
            dict_patterns,
            dict_terms,
            dict_taxonomy,
        )

        # Dictionary matched
        if taxonomy and status in ["Único", "Ambíguo"]:
            return ClassificationResult(
                status=status,
                n4=taxonomy.get("N4", ""),
                n3=taxonomy.get("N3", ""),
                n2=taxonomy.get("N2", ""),
                n1=taxonomy.get("N1", ""),
                matched_terms=matched,
                confidence=ml_confidence,
                source="Dictionary",
                ambiguous_n4s=[taxonomy.get("N4", "")] if status == "Ambíguo" else [],
            )

    # Decision 4: Try LLM (fallback for non-Padrão sectors)
    if use_llm_fallback:
        llm_results, _ = classify_items_with_llm(
            [description],
            sector=sector,
            client_context=client_context,
            custom_hierarchy=hierarchy,
        )
        if llm_results:
            llm_res = llm_results[0]
            if llm_res.get("N1") and llm_res.get("N1") not in INCOMPLETE_VALUES:
                return ClassificationResult(
                    status="Único",  # LLM usually returns one answer
                    n4=llm_res.get("N4", ""),
                    n3=llm_res.get("N3", ""),
                    n2=llm_res.get("N2", ""),
                    n1=llm_res.get("N1", ""),
                    matched_terms=[],
                    confidence=llm_res.get("confidence", 0.0),
                    source="LLM (UNSPSC)",
                    ambiguous_n4s=[],
                )

    # No match at all -> Não Classificado
    return ClassificationResult(
        status="Nenhum",
        n4="Não Identificado",
        n3="Não Identificado",
        n2="Não Identificado",
        n1="Não Identificado",
        matched_terms=[],
        confidence=ml_confidence,
        source="None",
    )


if __name__ == "__main__":
    # Test hybrid classification
    print("Testing Hybrid Classifier...")
    print("=" * 60)

    # This would require loading the dictionary which is not trivial here
    # For now just demonstrate the concept
    print("\nNote: Full test requires dictionary loading.")
    print("This module is designed to be imported and used in function_app.py")
