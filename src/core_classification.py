"""
Core classification pipeline for spend analysis.
Supports two paths:
1. Legacy ML path: ML -> Dictionary -> LLM fallback (for sectors with trained models)
2. New LLM-direct path (Two-Phase):
   Phase 1: KB direct match (sim >= 0.90) — no LLM call needed
   Phase 2: LLM with enriched per-batch KB examples -> hierarchy validation
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

from src.types import KBEntryDict, ClassificationResultDict, HierarchyEntryDict
from src.utils import INCOMPLETE_VALUES

logger = logging.getLogger(__name__)

# Two-phase KB learning thresholds
KB_DIRECT_MATCH_THRESHOLD = (
    0.90  # Min similarity to use KB classification directly (no LLM)
)
KB_ENRICHED_EXAMPLE_MIN_SIM = (
    0.30  # Min similarity to include as enriched example for LLM
)
KB_ENRICHED_MAX_EXAMPLES = 20  # Max enriched examples per LLM batch


def process_dataframe_chunk(
    df_chunk: pd.DataFrame,
    desc_column: str,
    sector: str = "Padrão",
    models_dir: Optional[str] = None,
    custom_hierarchy: Optional[List[HierarchyEntryDict]] = None,
    client_context: str = "",
    few_shot_examples: Optional[List[KBEntryDict]] = None,
    hierarchy_lookup: Optional[object] = None,
    use_legacy_ml: bool = False,
    project_id: Optional[str] = None,
    user_instruction: Optional[str] = None,
    kb_retriever: Optional[object] = None,
    use_web_search: bool = False,
    usage_sink: Optional[Dict[str, int]] = None,
) -> List[ClassificationResultDict]:
    """
    Classify a DataFrame chunk.

    Pipeline:
    1. If use_legacy_ml=True and sector has trained model: ML -> Dict -> LLM fallback
    2. Otherwise: Two-Phase LLM-direct with KB learning:
       Phase 1: KB direct match (sim >= 0.90) — instant, no LLM
       Phase 2: LLM with enriched per-batch examples from KB
    3. Hierarchy validation (if custom_hierarchy provided)

    Returns list of dicts with keys: description, N1, N2, N3, N4, source, confidence
    """
    descriptions = df_chunk[desc_column].astype(str).tolist()

    if use_legacy_ml and sector and sector != "Padrão":
        results = _legacy_ml_pipeline(
            df_chunk,
            sector,
            desc_column,
            models_dir,
            custom_hierarchy,
            hierarchy_lookup,
        )
    else:
        results = _llm_direct_pipeline(
            descriptions,
            sector,
            client_context,
            custom_hierarchy,
            few_shot_examples,
            hierarchy_lookup,
            user_instruction,
            kb_retriever=kb_retriever,
            use_web_search=use_web_search,
            usage_sink=usage_sink,
        )

    return results


def _llm_direct_pipeline(
    descriptions: List[str],
    sector: str,
    client_context: str,
    custom_hierarchy: Optional[List[HierarchyEntryDict]],
    few_shot_examples: Optional[List[KBEntryDict]],
    hierarchy_lookup: Optional[object],
    user_instruction: Optional[str] = None,
    kb_retriever: Optional[object] = None,
    use_web_search: bool = False,
    usage_sink: Optional[Dict[str, int]] = None,
) -> List[ClassificationResultDict]:
    """Two-Phase LLM-direct path:

    Phase 1: KB direct match — items with similarity >= KB_DIRECT_MATCH_THRESHOLD
             are classified instantly from KB (no LLM call).
    Phase 2: Remaining items sent to LLM with enriched per-batch examples
             (relevant KB matches for this specific batch, not global).
    """
    from src.llm_classifier import classify_items_with_llm
    from src.hierarchy_validator import validate_and_correct
    from src.kb_retriever import KBRetriever

    results = [None] * len(descriptions)
    remaining_indices = []

    # ── PHASE 1: Direct KB match ──
    batch_matches = None
    if kb_retriever and kb_retriever.matrix is not None:
        batch_matches = kb_retriever.retrieve_batch(descriptions, top_k=3)

        for i, (desc, matches) in enumerate(zip(descriptions, batch_matches)):
            best = matches[0] if matches else None
            # Only use KB direct match if: high similarity AND complete classification
            if (
                best
                and best["_similarity"] >= KB_DIRECT_MATCH_THRESHOLD
                and all(
                    str(best.get(lvl, "")).strip() not in INCOMPLETE_VALUES
                    for lvl in ("N1", "N2", "N3", "N4")
                )
            ):
                results[i] = {
                    "description": desc,
                    "N1": best.get("N1", "Não Identificado"),
                    "N2": best.get("N2", "Não Identificado"),
                    "N3": best.get("N3", "Não Identificado"),
                    "N4": best.get("N4", "Não Identificado"),
                    "source": "KB (Direct Match)",
                    "confidence": round(best["_similarity"], 3),
                }
            else:
                remaining_indices.append(i)
    else:
        remaining_indices = list(range(len(descriptions)))

    kb_direct_count = len(descriptions) - len(remaining_indices)
    if kb_direct_count > 0:
        logger.info(
            f"KB direct match: {kb_direct_count}/{len(descriptions)} items "
            f"({kb_direct_count / len(descriptions) * 100:.0f}%)"
        )

    # ── PHASE 2: LLM for items without direct match ──
    if remaining_indices:
        remaining_descs = [descriptions[i] for i in remaining_indices]

        # Select enriched examples based on partial matches for this batch
        enriched_examples = None
        if batch_matches:
            relevant_matches = [batch_matches[i] for i in remaining_indices]
            enriched_examples = KBRetriever.select_enriched_examples(
                relevant_matches, max_examples=KB_ENRICHED_MAX_EXAMPLES
            )

        # Fallback to global representative examples if no enriched matches
        if not enriched_examples and few_shot_examples:
            enriched_examples = KBRetriever.select_representative_examples(
                few_shot_examples, max_k=10
            )

        llm_results, llm_usage = classify_items_with_llm(
            remaining_descs,
            sector=sector or "Padrão",
            client_context=client_context,
            custom_hierarchy=custom_hierarchy,
            few_shot_examples=enriched_examples,
            user_instruction=user_instruction,
            use_web_search=use_web_search,
        )

        # Acumula token usage no sink (caller persiste no status.json do job)
        if usage_sink is not None and llm_usage:
            for k in (
                "prompt_tokens",
                "completion_tokens",
                "reasoning_tokens",
                "total_tokens",
            ):
                usage_sink[k] = usage_sink.get(k, 0) + int(llm_usage.get(k, 0))

        # Merge LLM results back into correct positions
        for j, orig_idx in enumerate(remaining_indices):
            if j < len(llm_results) and llm_results[j]:
                r = llm_results[j]
                results[orig_idx] = {
                    "description": descriptions[orig_idx],
                    "N1": r.get("N1", "Não Identificado"),
                    "N2": r.get("N2", "Não Identificado"),
                    "N3": r.get("N3", "Não Identificado"),
                    "N4": r.get("N4", "Não Identificado"),
                    "source": r.get("source", "LLM (Batch)"),
                    "confidence": r.get("confidence", 0.0),
                }
            else:
                results[orig_idx] = {
                    "description": descriptions[orig_idx],
                    "N1": "Não Identificado",
                    "N2": "Não Identificado",
                    "N3": "Não Identificado",
                    "N4": "Não Identificado",
                    "source": "None",
                    "confidence": 0.0,
                }

    # Hierarchy validation on ALL results (KB direct + LLM)
    if custom_hierarchy and hierarchy_lookup:
        results, stats = validate_and_correct(
            results, custom_hierarchy, lookup=hierarchy_lookup
        )
        logger.info(f"Hierarchy validation stats: {stats}")

    # Zero confidence for incomplete classifications
    for r in results:
        if r and any(
            str(r.get(lvl, "")).strip() in INCOMPLETE_VALUES
            for lvl in ("N1", "N2", "N3", "N4")
        ):
            r["confidence"] = 0.0

    return results


def _legacy_ml_pipeline(
    df_chunk: pd.DataFrame,
    sector: str,
    desc_column: str,
    models_dir: Optional[str],
    custom_hierarchy: Optional[List[HierarchyEntryDict]],
    hierarchy_lookup: Optional[object],
) -> List[ClassificationResultDict]:
    """Legacy path: Hybrid ML+Dictionary+LLM pipeline (from v2)."""
    # Import hybrid classifier (v2 compatible)
    try:
        from src.hybrid_classifier import classify_hybrid
        from src.ml_classifier import load_model_for_sector
        from src.hierarchy_validator import validate_and_correct
    except ImportError as e:
        logger.error(f"Legacy ML pipeline import error: {e}")
        descriptions = df_chunk[desc_column].astype(str).tolist()
        return [
            {
                "description": d,
                "N1": "Não Identificado",
                "N2": "Não Identificado",
                "N3": "Não Identificado",
                "N4": "Não Identificado",
                "status": "Nenhum",
                "source": "None",
                "confidence": 0.0,
                "matched_terms": [],
            }
            for d in descriptions
        ]

    results = []
    # Pass 1 & 2: ML + Dictionary per row (no LLM yet)
    ml_model, dict_patterns = load_model_for_sector(sector, models_dir)
    none_indices = []

    for idx, row in df_chunk.iterrows():
        desc = str(row[desc_column])
        try:
            classification = classify_hybrid(
                desc, ml_model, dict_patterns, use_llm_fallback=False
            )
            result = {
                "description": desc,
                "N1": classification.N1 or "Não Identificado",
                "N2": classification.N2 or "Não Identificado",
                "N3": classification.N3 or "Não Identificado",
                "N4": classification.N4 or "Não Identificado",
                "status": classification.status,
                "source": classification.source,
                "confidence": classification.confidence,
                "matched_terms": classification.matched_terms or [],
            }
        except Exception as e:
            logger.error(f"classify_hybrid error for '{desc}': {e}")
            result = {
                "description": desc,
                "N1": "Não Identificado",
                "N2": "Não Identificado",
                "N3": "Não Identificado",
                "N4": "Não Identificado",
                "status": "Nenhum",
                "source": "None",
                "confidence": 0.0,
                "matched_terms": [],
            }
        results.append(result)
        if result["status"] == "Nenhum":
            none_indices.append(len(results) - 1)

    # Pass 2: Batch LLM for "Nenhum" items
    if none_indices:
        from src.llm_classifier import classify_items_with_llm

        none_descs = [results[i]["description"] for i in none_indices]
        # Caminho legado ignora o usage (sem persistência de tokens)
        llm_results, _ = classify_items_with_llm(
            none_descs, sector=sector, custom_hierarchy=custom_hierarchy
        )
        for j, i in enumerate(none_indices):
            if j < len(llm_results) and llm_results[j]:
                r = llm_results[j]
                results[i].update(
                    {
                        "N1": r.get("N1", "Não Identificado"),
                        "N2": r.get("N2", "Não Identificado"),
                        "N3": r.get("N3", "Não Identificado"),
                        "N4": r.get("N4", "Não Identificado"),
                        "status": r.get("status", "Único"),
                        "source": r.get("source", "LLM (Batch)"),
                        "confidence": r.get("confidence", 0.0),
                    }
                )

    # Pass 3: Hierarchy validation
    if custom_hierarchy and hierarchy_lookup:
        results, stats = validate_and_correct(
            results, custom_hierarchy, lookup=hierarchy_lookup
        )

    return results
