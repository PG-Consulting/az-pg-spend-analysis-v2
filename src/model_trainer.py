"""
Model Trainer for Spend Analysis ML Classifier.
"""

import pandas as pd
import numpy as np
import logging
import joblib
import os
import json
import shutil
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, f1_score
from src.preprocessing import build_tfidf_vectorizer, normalize_text

def train_model_core(
    df: pd.DataFrame,
    sector: str = "varejo",
    models_dir: str = "models",
    test_size: float = 0.2,
    random_state: int = 42,
    training_filename: str = "dataset.csv"
):
    """
    Core function to train the ML classifier and save model artifacts.
    
    Args:
        df: DataFrame containing 'Beschreibung_Normalizada' (or equivalent) and 'N4' columns.
            It expects the dataframe to already have normalized descriptions.
        sector: Sector name (models will be saved to models/{sector}/).
        models_dir: Base directory for models.
        test_size: Fraction of data to use for validation.
        random_state: Random seed for reproducibility.
        training_filename: Name of the dataset file used for training, for history tracking.
        
    Returns:
        Dict with training metrics and artifacts.
    """
    # Sector-specific model directory
    sector_model_dir = os.path.join(models_dir, sector.lower())
    os.makedirs(sector_model_dir, exist_ok=True)
    
    # Versioning Setup - Incremental
    history_file = os.path.join(sector_model_dir, "model_history.json")
    next_version_num = 1
    
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
                if history:
                    # Extract numeric part of v_X
                    existing_versions = []
                    for h in history:
                        vid = h.get("version_id", "")
                        if vid.startswith("v_"):
                             try:
                                 num = int(vid.split("_")[1])
                                 existing_versions.append(num)
                             except ValueError:
                                 pass # If regex fails (e.g. old timestamp), ignore or handle
                    
                    if existing_versions:
                        next_version_num = max(existing_versions) + 1
        except Exception as e:
            logging.warning(f"Error reading history for versioning: {e}")
            
    version_id = f"v_{next_version_num}"
    version_dir = os.path.join(sector_model_dir, "versions", version_id)
    os.makedirs(version_dir, exist_ok=True)
    
    logging.info(f"Starting training for sector '{sector}' (Version: {version_id})...")
    logging.info("=" * 60)
    logging.info(f"ML CLASSIFIER TRAINING - Sector: {sector.upper()}")
    logging.info("=" * 60)
    
    logging.info(f"   Loaded {len(df)} examples")
    logging.info(f"   Unique N4 categories: {df['N4'].nunique()}")
    
    # Filter out rare categories (stratified split requires at least 2 per class)
    logging.info("2. Filtering rare N4 categories...")
    n4_counts = df['N4'].value_counts()
    min_examples = 5  # Minimum examples per category
    valid_n4s = n4_counts[n4_counts >= min_examples].index
    df_filtered = df[df['N4'].isin(valid_n4s)].copy()
    
    removed_count = len(df) - len(df_filtered)
    removed_categories = df['N4'].nunique() - df_filtered['N4'].nunique()
    
    logging.info(f"   Removed {removed_categories} categories with < {min_examples} examples")
    logging.info(f"   Removed {removed_count} examples ({removed_count/len(df)*100:.1f}% of data)")
    logging.info(f"   Remaining: {len(df_filtered)} examples, {df_filtered['N4'].nunique()} categories")
    # Identificar coluna de texto
    text_col = None
    if 'Descrição' in df_filtered.columns:
        text_col = 'Descrição'
    elif 'Item_Description' in df_filtered.columns:
        text_col = 'Item_Description'
    elif 'Descricao' in df_filtered.columns:
        text_col = 'Descricao'
    
    if not text_col:
        return {
            "success": False,
            "error": "Coluna de descrição não encontrada (Esperado: 'Descrição', 'Item_Description' ou 'Descricao')"
        }
    
    logging.info(f"   Using column '{text_col}' for training.")
    
    # Normalização
    # Se já tiver Descrição_Normalizada, usa. Senão, cria.
    if "Descrição_Normalizada" not in df_filtered.columns:
        logging.info("   Normalizing descriptions...")
        df_filtered["Descrição_Normalizada"] = df_filtered[text_col].astype(str).apply(normalize_text) # Uses internal normalize function if needed, or from taxonomy_engine
    
    # 2. Prepare Data (re-filtering after normalization and text column identification)
    # Filter valid N4
    if "N4" not in df_filtered.columns:
         return { "success": False, "error": "Coluna N4 não encontrada." }

    df_clean = df_filtered.dropna(subset=['Descrição_Normalizada', 'N4']).copy()
    
    # Filter "Nenhum" or "Ambíguo"
    df_clean = df_clean[~df_clean['N4'].isin(['Nenhum', 'Ambíguo'])]
    
    if len(df_clean) < 10:
        return {
            "success": False,
            "error": f"Dados insuficientes após limpeza. Encontrados {len(df_clean)} exemplos válidos."
        }
    
    X = df_clean['Descrição_Normalizada'].values
    y = df_clean['N4'].values
    
    # Encode labels to integers
    logging.info("3. Encoding N4 labels...")
    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)
    logging.info(f"   Encoded {len(label_encoder.classes_)} classes")
    
    # Split train/validation
    logging.info(f"4. Splitting data ({int((1-test_size)*100)}% train, {int(test_size*100)}% validation)...")
    X_train, X_val, y_train, y_val = train_test_split(
        X, y_encoded, 
        test_size=test_size, 
        random_state=random_state,
        stratify=y_encoded
    )
    logging.info(f"   Train set: {len(X_train)} examples")
    logging.info(f"   Validation set: {len(X_val)} examples")
    
    # Build TF-IDF vectorizer
    logging.info("5. Building TF-IDF vectorizer...")
    vectorizer = build_tfidf_vectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95
    )
    X_train_vec = vectorizer.fit_transform(X_train)
    X_val_vec = vectorizer.transform(X_val)
    logging.info(f"   Vocabulary size: {len(vectorizer.vocabulary_)}")
    logging.info(f"   Feature matrix shape: {X_train_vec.shape}")
    
    # Train classifier
    logging.info("6. Training Logistic Regression classifier...")
    classifier = LogisticRegression(
        C=1.0,
        max_iter=1000,
        n_jobs=-1,
        random_state=random_state,
        verbose=0,
        class_weight='balanced'  # Better F1 for minority classes
    )
    classifier.fit(X_train_vec, y_train)
    logging.info("   Training complete!")
    
    # Evaluate on validation set
    logging.info("7. Evaluating on validation set...")
    y_val_pred = classifier.predict(X_val_vec)
    accuracy = accuracy_score(y_val, y_val_pred)
    f1_macro = f1_score(y_val, y_val_pred, average='macro')
    f1_weighted = f1_score(y_val, y_val_pred, average='weighted')
    
    logging.info(f"   Validation Accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")
    
    # Confidence analysis
    logging.info("8. Analyzing prediction confidence...")
    y_val_proba = classifier.predict_proba(X_val_vec)
    max_probas = y_val_proba.max(axis=1)
    
    # Save model artifacts
    # Save model artifacts (VERSIONED)
    logging.info(f"9. Saving model artifacts to {version_dir}/...")
    
    joblib.dump(vectorizer, f"{version_dir}/tfidf_vectorizer.pkl")
    joblib.dump(classifier, f"{version_dir}/classifier.pkl")
    joblib.dump(label_encoder, f"{version_dir}/label_encoder.pkl")
    
    # Update Active Model (Copy from version to root)
    logging.info(f"   Updating active model in {sector_model_dir}/...")
    shutil.copy(f"{version_dir}/tfidf_vectorizer.pkl", f"{sector_model_dir}/tfidf_vectorizer.pkl")
    shutil.copy(f"{version_dir}/classifier.pkl", f"{sector_model_dir}/classifier.pkl")
    shutil.copy(f"{version_dir}/label_encoder.pkl", f"{sector_model_dir}/label_encoder.pkl")
    
    # Extract and save N4 hierarchy (N4 -> N1, N2, N3 mapping)
    logging.info("10. Extracting N4 hierarchy mapping...")
    hierarchy_file = os.path.join(sector_model_dir, "n4_hierarchy.json")
    
    # Check if N1, N2, N3 columns exist in the data
    hierarchy_cols = ['N1', 'N2', 'N3', 'N4']
    if all(col in df.columns for col in hierarchy_cols):
        # Extract unique N4 -> (N1, N2, N3) mapping from original data
        hierarchy_df = df[hierarchy_cols].drop_duplicates(subset=['N4'])
        hierarchy = {}
        for _, row in hierarchy_df.iterrows():
            n4 = str(row['N4']).strip()
            if n4 and n4.lower() not in ['nan', 'nenhum', 'ambíguo']:
                hierarchy[n4] = {
                    'N1': str(row['N1']).strip() if pd.notna(row['N1']) else '',
                    'N2': str(row['N2']).strip() if pd.notna(row['N2']) else '',
                    'N3': str(row['N3']).strip() if pd.notna(row['N3']) else ''
                }
        
        # Merge with existing hierarchy (don't lose old categories)
        if os.path.exists(hierarchy_file):
            try:
                with open(hierarchy_file, 'r', encoding='utf-8') as f:
                    existing_hierarchy = json.load(f)
                # Update existing with new (new data takes precedence)
                existing_hierarchy.update(hierarchy)
                hierarchy = existing_hierarchy
            except Exception as e:
                logging.warning(f"Could not load existing hierarchy: {e}")
        
        with open(hierarchy_file, 'w', encoding='utf-8') as f:
            json.dump(hierarchy, f, ensure_ascii=False, indent=2)
        
        # Also save versioned copy for rollback
        versioned_hierarchy_file = os.path.join(version_dir, "n4_hierarchy.json")
        with open(versioned_hierarchy_file, 'w', encoding='utf-8') as f:
            json.dump(hierarchy, f, ensure_ascii=False, indent=2)
        
        logging.info(f"   Saved hierarchy for {len(hierarchy)} N4 categories (+ versioned copy)")
    else:
        logging.warning(f"   N1/N2/N3 columns not found in training data. Hierarchy not updated.")
    
    # Update History JSON
    history_file = os.path.join(sector_model_dir, "model_history.json")
    history_entry = {
        "version_id": version_id,
        "timestamp": datetime.now().isoformat(),
        "filename": training_filename,
        "metrics": {
            "accuracy": round(accuracy, 4),
            "f1_macro": round(f1_macro, 4),
            "total_samples": len(df_filtered)
        },
        "status": "active" # The latest trained is always initially active
    }
    
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
                # Mark previous active as inactive
                for h in history:
                    h['status'] = 'inactive'
        except:
            pass
            
    history.insert(0, history_entry) # Add new at top
    
    # Limit Versions (Retention Policy: Keep max 3)
    MAX_VERSIONS = 3
    if len(history) > MAX_VERSIONS:
        # Identify versions to remove
        versions_to_remove = history[MAX_VERSIONS:]
        history = history[:MAX_VERSIONS]
        
        logging.info(f"Cleanup: Removing {len(versions_to_remove)} old versions (Max allowed: {MAX_VERSIONS})")
        
        for v in versions_to_remove:
            vid = v.get("version_id")
            v_dir = os.path.join(sector_model_dir, "versions", vid)
            if os.path.exists(v_dir):
                try:
                    shutil.rmtree(v_dir)
                    logging.info(f"   Deleted old version: {vid}")
                except Exception as e:
                    logging.warning(f"   Failed to delete {vid}: {e}")
    
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)
    
    # Return metrics and paths
    return {
        'accuracy': accuracy,
        'f1_macro': f1_macro,
        'f1_weighted': f1_weighted,
        'artifacts_dir': sector_model_dir,
        'confidence_stats': {
            'mean': max_probas.mean(),
            'median': pd.Series(max_probas).median(),
            'high_conf_pct': (max_probas >= 0.90).mean()
        }
    }


def train_model(sector: str, dataset_path: str, models_dir: str = "models") -> dict:
    """
    Wrapper function to train a model from a dataset file path.
    
    Args:
        sector: Sector name (e.g., 'varejo', 'educacional').
        dataset_path: Path to the CSV/Excel file containing training data.
        models_dir: Base directory for models (defaults to 'models', but should be
                    passed from caller when running in Azure).
        
    Returns:
        Dict with training results and metrics.
    """
    logging.info(f"Loading dataset from: {dataset_path}")
    logging.info(f"Models directory: {models_dir}")
    
    # Load the dataset
    try:
        if dataset_path.endswith('.csv'):
            df = pd.read_csv(dataset_path)
        else:
            df = pd.read_excel(dataset_path)
    except Exception as e:
        logging.error(f"Error loading dataset: {e}")
        return {"success": False, "error": f"Error loading dataset: {e}"}
    
    logging.info(f"Loaded {len(df)} rows from dataset")
    
    # Ensure normalized description column exists
    if 'Descrição_Normalizada' not in df.columns and 'Descrição' in df.columns:
        df['Descrição_Normalizada'] = df['Descrição'].astype(str).apply(normalize_text)
    
    # Get the training filename for history
    training_filename = os.path.basename(dataset_path)
    
    # Call the core training function
    result = train_model_core(
        df=df,
        sector=sector,
        models_dir=models_dir,
        training_filename=training_filename
    )
    
    # Format result for API response
    if isinstance(result, dict) and 'accuracy' in result:
        return {
            "success": True,
            "accuracy": result.get('accuracy', 0),
            "f1_macro": result.get('f1_macro', 0),
            "f1_weighted": result.get('f1_weighted', 0),
            "artifacts_dir": result.get('artifacts_dir', ''),
            "message": f"Model trained successfully for sector '{sector}'"
        }
    elif isinstance(result, dict) and 'error' in result:
        return {"success": False, "error": result.get('error')}
    else:
        return {"success": True, "result": result}
