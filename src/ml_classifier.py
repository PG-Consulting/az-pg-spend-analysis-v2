"""
ML Classifier for Spend Analysis.

This module provides the ML-based classification functionality with:
- Model loading and caching
- Prediction with confidence scores
- Complete taxonomy hierarchy (N1, N2, N3, N4) for each prediction
"""

import joblib
import json
import logging
import os
from typing import List, Tuple, Dict, Optional
import numpy as np
from src.preprocessing import normalize_text

logger = logging.getLogger(__name__)


# Global cache for loaded models (per sector)
_MODEL_CACHE = {}


def clear_model_cache(sector: str = None):
    """
    Clear the model cache to force reloading on next prediction.
    
    Args:
        sector: If provided, clear only this sector's cache. 
                If None, clear all cached models.
    """
    global _MODEL_CACHE
    if sector:
        sector = sector.lower().strip()
        if sector in _MODEL_CACHE:
            del _MODEL_CACHE[sector]
            logger.info(f"Cleared model cache for sector '{sector}'")
    else:
        _MODEL_CACHE = {}
        logger.info("Cleared all model caches")


def load_model(sector: str = "varejo", models_dir: str = "models") -> Tuple:
    """
    Load trained ML model artifacts for a specific sector with caching.
    
    Loads:
    - TF-IDF vectorizer
    - Logistic Regression classifier
    - Label encoder (N4 categories)
    - N4 hierarchy mapping (N4 -> N1, N2, N3)
    
    Args:
        sector: Sector name (e.g., 'varejo', 'industrial'). Models are loaded from models/{sector}/
        models_dir: Base directory containing sector subdirectories.
    
    Returns:
        Tuple of (vectorizer, classifier, label_encoder, hierarchy_mapping)
    """
    # Normalize sector name (lowercase for consistency)
    sector = sector.lower().strip()
    
    # Return cached models if already loaded for this sector
    if sector in _MODEL_CACHE and all(v is not None for v in _MODEL_CACHE[sector].values()):
        return (
            _MODEL_CACHE[sector]['vectorizer'],
            _MODEL_CACHE[sector]['classifier'],
            _MODEL_CACHE[sector]['label_encoder'],
            _MODEL_CACHE[sector]['hierarchy']
        )
    
    # Sector-specific model directory
    sector_model_dir = os.path.join(models_dir, sector)
    
    if not os.path.exists(sector_model_dir):
        raise FileNotFoundError(
            f"Model directory for sector '{sector}' not found: {sector_model_dir}. "
            f"Please train models for this sector first."
        )
    
    logger.info(f"Loading ML model for sector '{sector}' from {sector_model_dir}/...")
    
    # Initialize cache for this sector
    if sector not in _MODEL_CACHE:
        _MODEL_CACHE[sector] = {
            'vectorizer': None,
            'classifier': None,
            'label_encoder': None,
            'hierarchy': None
        }
    
    # Load vectorizer
    vectorizer_path = os.path.join(sector_model_dir, "tfidf_vectorizer.pkl")
    _MODEL_CACHE[sector]['vectorizer'] = joblib.load(vectorizer_path)
    logger.info(f"  [SUCCESS] Loaded vectorizer")

    # Load classifier
    classifier_path = os.path.join(sector_model_dir, "classifier.pkl")
    _MODEL_CACHE[sector]['classifier'] = joblib.load(classifier_path)
    logger.info(f"  [SUCCESS] Loaded classifier")

    # Load label encoder
    encoder_path = os.path.join(sector_model_dir, "label_encoder.pkl")
    _MODEL_CACHE[sector]['label_encoder'] = joblib.load(encoder_path)
    logger.info(f"  [SUCCESS] Loaded label encoder ({len(_MODEL_CACHE[sector]['label_encoder'].classes_)} classes)")

    # Load hierarchy mapping
    hierarchy_path = os.path.join(sector_model_dir, "n4_hierarchy.json")
    with open(hierarchy_path, 'r', encoding='utf-8') as f:
        _MODEL_CACHE[sector]['hierarchy'] = json.load(f)
    logger.info(f"  [SUCCESS] Loaded hierarchy mapping")

    logger.info(f"ML model for sector '{sector}' loaded successfully!")
    
    return (
        _MODEL_CACHE[sector]['vectorizer'],
        _MODEL_CACHE[sector]['classifier'],
        _MODEL_CACHE[sector]['label_encoder'],
        _MODEL_CACHE[sector]['hierarchy']
    )


def load_model_for_sector(sector: str, models_dir: str = None) -> Tuple:
    """
    Load ALL model components for a sector, including ML models and Dictionary patterns.

    This matches the signature expected by core_classification.py:
        ml_model, dict_patterns = load_model_for_sector(sector, models_dir)
    where:
        ml_model      = (vectorizer, classifier, label_encoder, hierarchy)
        dict_patterns = (patterns, terms, taxonomy)
    """
    import pandas as pd
    from src.taxonomy_engine import build_patterns

    if models_dir is None:
        models_dir = "models"

    # 1. Load ML Model (Standard)
    try:
        if sector.strip().capitalize() == "Padrão":
             # Padrão usually uses LLM only, but we return Nones for ML
             vectorizer, classifier, label_encoder, hierarchy = None, None, None, None
        else:
             vectorizer, classifier, label_encoder, hierarchy = load_model(sector, models_dir)
    except Exception as e:
        logger.warning(f"Warning: ML model not found for {sector}: {e}")
        vectorizer, classifier, label_encoder, hierarchy = None, None, None, None

    # 2. Load Dictionary Patterns (Default)
    # Try to find Spend_Taxonomy.xlsx in current directory or parent
    patterns, terms, taxonomy = {}, {}, {}
    
    # Potential paths for the dictionary
    possible_paths = [
        "Spend_Taxonomy.xlsx",
        "../Spend_Taxonomy.xlsx",
        "/home/site/wwwroot/Spend_Taxonomy.xlsx"
    ]
    
    dict_path = None
    for p in possible_paths:
        if os.path.exists(p):
            dict_path = p
            break
            
    if dict_path:
        try:
            logger.info(f"Loading dictionary from {dict_path} for sector {sector}...")
            # We assume the dictionary file has sheets. We need to find the right logical subset?
            # Actually build_patterns takes a DataFrame.
            # Usually the dictionary file has ALL sectors. We need to filter?
            # Spend_Taxonomy.xlsx usually has a "Base" sheet or similar.
            # BUT, usually 'build_patterns' expects a DF with columns N1, N2...
            # If we load the whole file, we might get a mix.
            # For "Padrão", we might not use this.
            # For "Varejo", we might want to filter by sector if the column exists?
            # Let's just load it raw.
            
            # Note: This is an expensive operation. Ideally cached.
            # But local worker is long running, so maybe we cache results in _MODEL_CACHE?
            
            cached_patterns = _MODEL_CACHE.get(sector, {}).get('patterns')
            if cached_patterns:
                 patterns, terms, taxonomy = cached_patterns
            else:
                xl = pd.ExcelFile(dict_path)
                # Heuristic: Find first sheet that looks like data
                sheet = xl.sheet_names[0]
                for s in xl.sheet_names:
                    if "base" in s.lower() or "dados" in s.lower() or "taxonomy" in s.lower():
                        sheet = s
                        break
                
                df_dict = pd.read_excel(dict_path, sheet_name=sheet)
                
                # Filter by sector if feasible? 
                # Start simple: pass the whole DF to build_patterns.
                patterns, terms, taxonomy = build_patterns(df_dict)
                
                # Update cache
                if sector not in _MODEL_CACHE: _MODEL_CACHE[sector] = {}
                _MODEL_CACHE[sector]['patterns'] = (patterns, terms, taxonomy)
                
        except Exception as e:
            logger.error(f"Failed to load dictionary patterns: {e}")
    else:
        logger.warning("Spend_Taxonomy.xlsx not found. Running without dictionary patterns.")

    ml_model = (vectorizer, classifier, label_encoder, hierarchy)
    dict_patterns = (patterns, terms, taxonomy)
    return ml_model, dict_patterns


def predict(
    texts: List[str],
    sector: str = "varejo",
    vectorizer=None,
    classifier=None,
    label_encoder=None,
    hierarchy=None,
    top_k: int = 3
) -> List[Dict]:
    """
    Predict N4 categories for a list of texts using the ML model.
    
    Args:
        texts: List of item descriptions (raw or normalized).
        sector: Sector name for model selection.
        vectorizer: TF-IDF vectorizer (loaded if None).
        classifier: Trained classifier (loaded if None).
        label_encoder: Label encoder (loaded if None).
        hierarchy: N4 hierarchy mapping (loaded if None).
        top_k: Number of top predictions to return for ambiguous cases.
    
    Returns:
        List of dictionaries, one per text, containing:
        - n4_predicted: Top predicted N4 category
        - confidence: Probability of top prediction (0-1)
        - n1, n2, n3: Hierarchy levels for the predicted N4
        - top_candidates: List of top K (N4, confidence, N1, N2, N3) tuples
    """
    # Load models if not provided
    if any(x is None for x in [vectorizer, classifier, label_encoder, hierarchy]):
        vectorizer, classifier, label_encoder, hierarchy = load_model(sector=sector)
    
    # Normalize texts
    texts_normalized = [normalize_text(text) for text in texts]
    
    # Vectorize
    X = vectorizer.transform(texts_normalized)
    
    # Predict probabilities
    probas = classifier.predict_proba(X)
    
    # Build results
    results = []
    for i, text_probas in enumerate(probas):
        # Get top K predictions
        top_k_indices = np.argsort(text_probas)[::-1][:top_k]
        top_k_n4s = label_encoder.inverse_transform(top_k_indices)
        top_k_probas = text_probas[top_k_indices]
        
        # Top prediction
        n4_predicted = top_k_n4s[0]
        confidence = top_k_probas[0]
        
        # Get hierarchy for top prediction
        n4_hierarchy = hierarchy.get(n4_predicted, {})
        n1 = n4_hierarchy.get('N1', '')
        n2 = n4_hierarchy.get('N2', '')
        n3 = n4_hierarchy.get('N3', '')
        
        # Build top candidates with hierarchy
        top_candidates = []
        for n4, prob in zip(top_k_n4s, top_k_probas):
            n4_hier = hierarchy.get(n4, {})
            top_candidates.append({
                'N4': n4,
                'confidence': float(prob),
                'N1': n4_hier.get('N1', ''),
                'N2': n4_hier.get('N2', ''),
                'N3': n4_hier.get('N3', '')
            })
        
        results.append({
            'n4_predicted': n4_predicted,
            'confidence': float(confidence),
            'N1': n1,
            'N2': n2,
            'N3': n3,
            'N4': n4_predicted,
            'top_candidates': top_candidates
        })
    
    return results


def predict_single(
    text: str,
    sector: str = "varejo",
    vectorizer=None,
    classifier=None,
    label_encoder=None,
    hierarchy=None,
    top_k: int = 3
) -> Dict:
    """
    Predict N4 category for a single text.
    
    Convenience wrapper around predict() for single texts.
    
    Args:
        text: Item description.
        sector: Sector name for model selection.
        vectorizer: TF-IDF vectorizer (loaded if None).
        classifier: Trained classifier (loaded if None).
        label_encoder: Label encoder (loaded if None).
        hierarchy: N4 hierarchy mapping (loaded if None).
        top_k: Number of top predictions to return.
    
    Returns:
        Dictionary with prediction results (same format as predict()).
    """
    results = predict([text], sector, vectorizer, classifier, label_encoder, hierarchy, top_k)
    return results[0]



# Alias for compatibility with core_classification.py
predict_batch = predict

if __name__ == "__main__":
    # Test the classifier
    logger.info("Testing ML Classifier...")
    logger.info("=" * 60)

    # Example texts
    test_texts = [
        "CAFE GRAOS 1KG",
        "ETIQUETA ADESIVA BRANCA",
        "FRETE RODOVIARIO SAO PAULO"
    ]

    logger.info("\nTest predictions:")
    logger.info("-" * 60)

    for text in test_texts:
        result = predict_single(text)
        logger.info(f"\nText: {text}")
        logger.info(f"Predicted N4: {result['n4_predicted']}")
        logger.info(f"Confidence: {result['confidence']:.4f}")
        logger.info(f"Hierarchy: {result['N1']} > {result['N2']} > {result['N3']} > {result['N4']}")
        logger.info("Top 3 candidates:")
        for j, cand in enumerate(result['top_candidates'], 1):
            logger.info(f"  {j}. {cand['N4']} (conf: {cand['confidence']:.4f})")
