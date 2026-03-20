"""Blueprint for ML model management endpoints (training, history, rollback, info, training data)."""

import os
import io
import json
import base64
import logging
import shutil
from datetime import datetime

import azure.functions as func
from src.utils import get_models_dir
from src.api_helpers import (
    json_response,
    options_response,
    handle_errors,
)
from src.exceptions import NotFoundError, ValidationError
from src.auth import require_auth

logger = logging.getLogger(__name__)
models_bp = func.Blueprint()


def _load_hierarchy_with_fallback(sector_dir: str, version_id: str) -> dict:
    """Load N4 hierarchy for a given version, with multiple fallback strategies:
    1. Version-specific n4_hierarchy.json
    2. CSV reconstruction filtering rows up to target version
    3. Root n4_hierarchy.json (active model)
    Returns a dict keyed by N4.
    """
    import pandas as pd

    hierarchy = {}
    hierarchy_loaded = False

    # 1. Try version-specific hierarchy file
    if version_id and version_id != "active":
        version_hierarchy = os.path.join(
            sector_dir, "versions", version_id, "n4_hierarchy.json"
        )
        if os.path.exists(version_hierarchy):
            try:
                with open(version_hierarchy, "r", encoding="utf-8") as f:
                    hierarchy = json.load(f)
                hierarchy_loaded = True
            except Exception:
                pass

    # 2. Fallback to CSV reconstruction
    if not hierarchy_loaded and version_id and version_id != "active":
        training_file = os.path.join(sector_dir, "dataset_master.csv")
        if os.path.exists(training_file):
            try:
                df = pd.read_csv(training_file)
                if "added_version" in df.columns:

                    def get_version_num(v):
                        try:
                            return int(str(v).replace("v_", "").replace("legacy", "0"))
                        except Exception:
                            return 0

                    target_v = get_version_num(version_id)
                    df["_v"] = df["added_version"].apply(get_version_num)
                    df_filtered = df[df["_v"] <= target_v]

                    if len(df_filtered) > 0 and "N4" in df_filtered.columns:
                        for _, row in (
                            df_filtered[["N1", "N2", "N3", "N4"]]
                            .drop_duplicates()
                            .iterrows()
                        ):
                            n4 = str(row["N4"]).strip()
                            if pd.notna(n4) and n4:
                                hierarchy[n4] = {
                                    "N1": str(row["N1"]).strip()
                                    if pd.notna(row["N1"])
                                    else "",
                                    "N2": str(row["N2"]).strip()
                                    if pd.notna(row["N2"])
                                    else "",
                                    "N3": str(row["N3"]).strip()
                                    if pd.notna(row["N3"])
                                    else "",
                                }
                        hierarchy_loaded = True
            except Exception as e:
                logger.warning(f"Failed to reconstruct hierarchy from CSV: {e}")

    # 3. Fallback to root n4_hierarchy.json
    if not hierarchy_loaded:
        hierarchy_file = os.path.join(sector_dir, "n4_hierarchy.json")
        if os.path.exists(hierarchy_file):
            try:
                with open(hierarchy_file, "r", encoding="utf-8") as f:
                    hierarchy = json.load(f)
            except Exception:
                pass

    return hierarchy


@models_bp.route(
    route="TrainModel", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS
)
@handle_errors("TrainModel")
@require_auth
def TrainModel(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/TrainModel
    Train a model for a specific sector using a provided classification file.

    Body:
        fileContent (str): Base64-encoded Excel or CSV with Descricao, N1, N2, N3, N4 columns.
        sector (str): Sector name. Use 'Padrao' for memory/RAG ingestion.
        filename (str, optional): Original filename for logging.

    Returns: {status, message, version, total_samples, report}
    """
    import pandas as pd

    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    logger.info("TrainModel HTTP trigger processed a request.")

    body = req.get_json()

    file_content_b64 = body.get("fileContent")
    sector = body.get("sector")
    filename = body.get("filename", "dataset.csv")

    if not file_content_b64 or not sector:
        raise ValidationError("Missing fileContent or sector")

    models_dir = get_models_dir()

    # Handle 'Padrao' sector (RAG Memory ingestion)
    if sector in ("Padrao", "Padrão"):
        logger.info("Sector is 'Padrao'. Initiating Memory ingestion (RAG)...")
        import tempfile
        import uuid as uuid_mod
        from src.memory_engine import MemoryEngine

        file_data = base64.b64decode(file_content_b64)
        temp_path = os.path.join(
            tempfile.gettempdir(), f"train_memory_{uuid_mod.uuid4()}.xlsx"
        )
        with open(temp_path, "wb") as f:
            f.write(file_data)

        engine = MemoryEngine()
        result = engine.ingest(temp_path)

        if os.path.exists(temp_path):
            os.remove(temp_path)

        if result["success"]:
            return json_response(
                {
                    "message": result["message"],
                    "accuracy": 1.0,
                    "f1_score": 1.0,
                    "confusion_matrix": "N/A - Regras Aprendidas",
                    "classification_report": "Memoria Atualizada",
                },
                request=req,
            )
        else:
            raise RuntimeError(f"Erro na ingestao de memoria: {result['message']}")

    # Standard ML training
    sector = sector.strip().capitalize()

    try:
        file_bytes = base64.b64decode(file_content_b64)
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception:
            try:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    sep=";",
                    encoding="utf-8",
                    on_bad_lines="skip",
                )
            except Exception:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    sep=",",
                    encoding="utf-8",
                    on_bad_lines="skip",
                )
    except Exception as e:
        raise ValidationError(f"Error reading file: {e}")

    from src.taxonomy_engine import normalize_text
    from src.preprocessing import normalize_header

    df.rename(columns=lambda x: normalize_header(x), inplace=True)

    required_cols = ["Descricao", "N1", "N2", "N3", "N4"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValidationError(
            f"Missing required columns: {missing}. Expected 'Descricao', 'N1', 'N2', 'N3', 'N4'."
        )

    logger.info("Training using Description='Descricao' and Label='N4'")

    df["Item_Description"] = df["Descricao"].fillna("")
    df["Descricao_Normalizada"] = df["Item_Description"].map(normalize_text)

    df_new = df[
        df["N4"].notna()
        & (df["N4"] != "")
        & (df["N4"] != "Nenhum")
        & (df["N4"] != "Ambíguo")
    ].copy()

    if len(df_new) < 1:
        raise ValidationError("No valid classified data found in uploaded file.")

    sector_lower = sector.lower()
    sector_dir = os.path.join(models_dir, sector_lower)
    os.makedirs(sector_dir, exist_ok=True)

    master_file = os.path.join(sector_dir, "dataset_master.csv")

    df_master = pd.DataFrame()
    if os.path.exists(master_file):
        try:
            df_master = pd.read_csv(master_file, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not read master dataset: {e}. Starting fresh.")

    cols_to_keep = ["Descricao", "N1", "N2", "N3", "N4", "Descricao_Normalizada"]

    history_file = os.path.join(sector_dir, "model_history.json")
    next_version = "v_1"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history = json.load(f)
            if history:
                existing_versions = [
                    int(h.get("version_id", "v_0").replace("v_", "")) for h in history
                ]
                next_version = f"v_{max(existing_versions) + 1}"
        except Exception:
            pass

    df_new_subset = df_new[cols_to_keep].copy()
    df_new_subset["added_version"] = next_version
    df_new_subset["added_at"] = datetime.now().isoformat()

    if not df_master.empty:
        if (
            "Descricao_Normalizada" not in df_master.columns
            and "Descricao" in df_master.columns
        ):
            df_master["Descricao_Normalizada"] = df_master["Descricao"].map(
                normalize_text
            )

        if "added_version" not in df_master.columns:
            df_master["added_version"] = "legacy"
        if "added_at" not in df_master.columns:
            df_master["added_at"] = ""

        all_cols = list(
            set(df_master.columns.tolist() + df_new_subset.columns.tolist())
        )
        for col in all_cols:
            if col not in df_master.columns:
                df_master[col] = ""
            if col not in df_new_subset.columns:
                df_new_subset[col] = ""

        df_combined = pd.concat([df_master, df_new_subset], ignore_index=True)
        logger.info(
            f"Combined: {len(df_master)} + {len(df_new_subset)} = {len(df_combined)} rows"
        )
    else:
        df_combined = df_new_subset
        logger.info(f"No existing master, starting with {len(df_combined)} rows")

    before_dedup = len(df_combined)
    df_combined.drop_duplicates(
        subset=["Descricao_Normalizada", "N4"], keep="first", inplace=True
    )
    logger.info(f"Deduplication: {before_dedup} -> {len(df_combined)} rows")

    df_combined.to_csv(master_file, index=False)
    logger.info(f"Saved master dataset with {len(df_combined)} rows")

    from src.model_trainer import train_model

    logger.info(f"Starting model training for sector {sector}...")
    report = train_model(sector=sector, dataset_path=master_file, models_dir=models_dir)
    logger.info("Training completed successfully.")

    return json_response(
        {
            "status": "success",
            "message": f"Modelo para setor '{sector}' treinado com sucesso!",
            "version": next_version,
            "total_samples": len(df_combined),
            "report": report,
        },
        request=req,
    )


@models_bp.route(
    route="GetModelHistory",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetModelHistory")
@require_auth
def GetModelHistory(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetModelHistory?sector=xxx
    Get training history for a sector.
    Returns: list of version records [{version_id, status, metrics, ...}]
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    sector = req.params.get("sector")
    if not sector:
        raise ValidationError("Missing 'sector' query parameter")

    sector = sector.strip().lower()
    models_dir = get_models_dir()
    history_file = os.path.join(models_dir, sector, "model_history.json")

    if not os.path.exists(history_file):
        return json_response([], request=req)

    with open(history_file, "r", encoding="utf-8") as f:
        history = json.load(f)
    return json_response(history, request=req)


@models_bp.route(
    route="SetActiveModel",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("SetActiveModel")
@require_auth
def SetActiveModel(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/SetActiveModel
    Roll back to a previous model version.
    Body: {sector, version_id}
    Returns: {message}
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    req_body = req.get_json()
    sector = req_body.get("sector")
    version_id = req_body.get("version_id")

    if not sector or not version_id:
        raise ValidationError("Missing sector or version_id")

    models_dir = get_models_dir()
    sector_dir = os.path.join(models_dir, sector.lower())
    version_dir = os.path.join(sector_dir, "versions", version_id)

    if not os.path.exists(version_dir):
        raise NotFoundError("Version", version_id)

    # Copy artifacts from version to root sector directory
    shutil.copy(
        f"{version_dir}/tfidf_vectorizer.pkl", f"{sector_dir}/tfidf_vectorizer.pkl"
    )
    shutil.copy(f"{version_dir}/classifier.pkl", f"{sector_dir}/classifier.pkl")
    shutil.copy(f"{version_dir}/label_encoder.pkl", f"{sector_dir}/label_encoder.pkl")

    versioned_hierarchy = f"{version_dir}/n4_hierarchy.json"
    if os.path.exists(versioned_hierarchy):
        shutil.copy(versioned_hierarchy, f"{sector_dir}/n4_hierarchy.json")
        logger.info(f"Restored n4_hierarchy.json from {version_id}")

    # Update model_history.json to mark the new active version
    history_file = f"{sector_dir}/model_history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history = json.load(f)
            for h in history:
                if h.get("version_id") == version_id:
                    h["status"] = "active"
                else:
                    h["status"] = "inactive"
            with open(history_file, "w") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error updating model history status: {e}")

    return json_response(
        {"message": f"Successfully rolled back to {version_id}"}, request=req
    )


@models_bp.route(
    route="GetModelInfo",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetModelInfo")
@require_auth
def GetModelInfo(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetModelInfo?sector=xxx&version_id=yyy
    Get detailed model info: hierarchy counts, training stats, metrics, and comparison with previous version.

    Query params:
        sector (required): Sector name.
        version_id (optional): Version ID. Defaults to active version.
    """
    import pandas as pd

    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    sector = req.params.get("sector")
    version_id = req.params.get("version_id")

    if not sector:
        raise ValidationError("Missing 'sector' parameter.")

    models_dir = get_models_dir()
    sector_dir = os.path.join(models_dir, sector.lower())

    hierarchy = _load_hierarchy_with_fallback(sector_dir, version_id)
    tree = {}

    for n4, levels in hierarchy.items():
        n1 = levels.get("N1", "Outros")
        n2 = levels.get("N2", "Outros")
        n3 = levels.get("N3", "Outros")
        if n1 not in tree:
            tree[n1] = {}
        if n2 not in tree[n1]:
            tree[n1][n2] = {}
        if n3 not in tree[n1][n2]:
            tree[n1][n2][n3] = []
        if n4 not in tree[n1][n2][n3]:
            tree[n1][n2][n3].append(n4)

    n1s = set(levels.get("N1", "") for levels in hierarchy.values())
    n2s = set(levels.get("N2", "") for levels in hierarchy.values())
    n3s = set(levels.get("N3", "") for levels in hierarchy.values())
    n4s = set(hierarchy.keys())

    training_stats = {"total_descriptions": 0, "by_n4": []}
    comparison = None
    metrics = {}
    active_version = None

    training_file = os.path.join(sector_dir, "dataset_master.csv")
    df_master = None
    if os.path.exists(training_file):
        try:
            df_master = pd.read_csv(training_file)
        except Exception as e:
            logger.warning(f"Error loading training data: {e}")

    def calc_stats_from_df(df, target_ver):
        count = 0
        n4_top = []
        if df is not None and "added_version" in df.columns:

            def get_version_num(v):
                try:
                    return int(str(v).replace("v_", "").replace("legacy", "0"))
                except Exception:
                    return 0

            target_v_num = get_version_num(target_ver)
            if "_version_num" not in df.columns:
                df = df.copy()
                df["_version_num"] = df["added_version"].apply(get_version_num)

            df_filtered = df[df["_version_num"] <= target_v_num]
            count = len(df_filtered)
            if "N4" in df_filtered.columns:
                n4_counts = df_filtered["N4"].value_counts().head(50)
                n4_top = [{"N4": n4, "count": int(c)} for n4, c in n4_counts.items()]
        elif df is not None:
            count = len(df)
            if "N4" in df.columns:
                n4_counts = df["N4"].value_counts().head(50)
                n4_top = [{"N4": n4, "count": int(c)} for n4, c in n4_counts.items()]
        return count, n4_top

    history_file = os.path.join(sector_dir, "model_history.json")
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history = json.load(f)
        except Exception:
            pass

    target_vid = version_id
    if not target_vid:
        for h in history:
            if h.get("status") == "active":
                active_version = h.get("version_id")
                target_vid = active_version
                break
        if not target_vid and history:
            target_vid = history[0]["version_id"]

    curr_idx = -1
    if target_vid:
        for i, h in enumerate(history):
            if h["version_id"] == target_vid:
                metrics = h.get("metrics", {})
                curr_idx = i
                break

    curr_samples, curr_n4_top = calc_stats_from_df(df_master, target_vid)
    training_stats["total_descriptions"] = curr_samples
    training_stats["by_n4"] = curr_n4_top

    if curr_idx != -1 and curr_idx + 1 < len(history):
        prev = history[curr_idx + 1]
        prev_vid = prev["version_id"]
        prev_metrics = prev.get("metrics", {})
        prev_samples, _ = calc_stats_from_df(df_master, prev_vid)
        prev_hierarchy = _load_hierarchy_with_fallback(sector_dir, prev_vid)
        p_n1s = set(levels.get("N1", "") for levels in prev_hierarchy.values())
        p_n2s = set(levels.get("N2", "") for levels in prev_hierarchy.values())
        p_n3s = set(levels.get("N3", "") for levels in prev_hierarchy.values())
        p_n4s = set(prev_hierarchy.keys())

        comparison = {
            "previous_version": prev_vid,
            "metrics": {
                "accuracy": prev_metrics.get("accuracy", 0),
                "f1_macro": prev_metrics.get("f1_macro", 0),
                "total_samples": prev_samples,
                "n1_count": len(p_n1s),
                "n2_count": len(p_n2s),
                "n3_count": len(p_n3s),
                "n4_count": len(p_n4s),
            },
        }

    response = {
        "sector": sector,
        "version_id": target_vid or "unknown",
        "hierarchy": {
            "N1_count": len(n1s),
            "N2_count": len(n2s),
            "N3_count": len(n3s),
            "N4_count": len(n4s),
            "tree": tree,
        },
        "training_stats": training_stats,
        "metrics": metrics,
        "comparison": comparison,
    }

    return json_response(response, request=req)


@models_bp.route(
    route="GetTrainingData",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetTrainingData")
@require_auth
def GetTrainingData(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetTrainingData?sector=xxx&page=1&page_size=50&version=...&n4=...&search=...
    Get paginated training data from dataset_master.csv.

    Query params:
        sector (required): Sector name.
        page (optional): Page number (default 1).
        page_size (optional): Items per page (default 50, max 200).
        version (optional): Filter by added_version.
        n4 (optional): Filter by N4 category.
        search (optional): Search text in description.
    """
    import pandas as pd

    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    sector = req.params.get("sector")
    if not sector:
        raise ValidationError("Missing 'sector' parameter.")

    page = int(req.params.get("page", 1))
    page_size = min(int(req.params.get("page_size", 50)), 200)
    version_filter = req.params.get("version")
    n4_filter = req.params.get("n4")
    search_filter = req.params.get("search")

    models_dir = get_models_dir()
    sector_dir = os.path.join(models_dir, sector.lower())
    master_file = os.path.join(sector_dir, "dataset_master.csv")

    if not os.path.exists(master_file):
        return json_response(
            {"data": [], "total": 0, "page": page, "page_size": page_size},
            request=req,
        )

    df = pd.read_csv(master_file)

    # Group duplicates and count occurrences for display
    desc_col = "Descricao" if "Descricao" in df.columns else df.columns[0]
    df["_count"] = df.groupby([desc_col, "N4", "added_version"])[desc_col].transform(
        "count"
    )
    df_display = df.drop_duplicates(
        subset=[desc_col, "N4", "added_version"], keep="first"
    ).copy()
    df_display.rename(columns={"_count": "Ocorrencias"}, inplace=True)

    # Apply filters
    if version_filter:
        df_display = df_display[df_display["added_version"] == version_filter]
    if n4_filter:
        df_display = df_display[df_display["N4"] == n4_filter]
    if search_filter:
        df_display = df_display[
            df_display[desc_col].str.contains(search_filter, case=False, na=False)
        ]

    total = len(df_display)
    total_with_duplicates = len(df)

    start = (page - 1) * page_size
    end = start + page_size
    df_page = df_display.iloc[start:end].reset_index()
    df_page.rename(columns={"index": "row_id"}, inplace=True)

    data = df_page.to_dict("records")
    versions = (
        df["added_version"].dropna().unique().tolist()
        if "added_version" in df.columns
        else []
    )

    response = {
        "data": data,
        "total": total,
        "total_with_duplicates": total_with_duplicates,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "versions": versions,
    }

    return json_response(response, request=req)


@models_bp.route(
    route="DeleteTrainingData",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("DeleteTrainingData")
@require_auth
def DeleteTrainingData(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/DeleteTrainingData
    Delete training data rows from dataset_master.csv.

    Body:
        sector (required): Sector name.
        row_ids (optional): List of row indices to delete (legacy).
        version (optional): Delete all rows from this version.
        items (optional): List of {descricao, n4, version} to delete all occurrences.
    """
    import pandas as pd

    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    body = req.get_json()

    sector = body.get("sector")
    row_ids = body.get("row_ids", [])
    version = body.get("version")
    items = body.get("items", [])

    if not sector:
        raise ValidationError("Missing 'sector' parameter.")

    if not row_ids and not version and not items:
        raise ValidationError(
            "Must provide 'row_ids', 'version', or 'items' to delete."
        )

    models_dir = get_models_dir()
    sector_dir = os.path.join(models_dir, sector.lower())
    master_file = os.path.join(sector_dir, "dataset_master.csv")

    if not os.path.exists(master_file):
        raise NotFoundError("Training data", sector)

    df = pd.read_csv(master_file)
    original_count = len(df)
    desc_col = "Descricao" if "Descricao" in df.columns else df.columns[0]

    if version:
        df = df[df["added_version"] != version]
        deleted_count = original_count - len(df)

        history_file = os.path.join(sector_dir, "model_history.json")
        if os.path.exists(history_file):
            with open(history_file, "r") as f:
                history = json.load(f)

            was_active = any(
                h.get("version_id") == version and h.get("status") == "active"
                for h in history
            )
            history = [h for h in history if h.get("version_id") != version]

            if was_active and history:
                history[0]["status"] = "active"
                new_active = history[0]["version_id"]
                version_dir = os.path.join(sector_dir, "versions", new_active)

                for artifact in (
                    "model.pkl",
                    "classifier.pkl",
                    "tfidf_vectorizer.pkl",
                    "label_encoder.pkl",
                    "n4_hierarchy.json",
                ):
                    src = os.path.join(version_dir, artifact)
                    dst = os.path.join(sector_dir, artifact)
                    if os.path.exists(src):
                        shutil.copy2(src, dst)

            with open(history_file, "w") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)

            version_folder = os.path.join(sector_dir, "versions", version)
            if os.path.exists(version_folder):
                shutil.rmtree(version_folder)

    elif items:
        for item in items:
            desc = item.get("descricao") or item.get("Descricao")
            n4 = item.get("n4") or item.get("N4")
            item_version = item.get("version") or item.get("added_version")
            if desc and n4 and item_version:
                mask = (
                    (df[desc_col] == desc)
                    & (df["N4"] == n4)
                    & (df["added_version"] == item_version)
                )
                df = df[~mask]
        deleted_count = original_count - len(df)
    else:
        df = df.drop(index=row_ids, errors="ignore")
        deleted_count = original_count - len(df)

    df.to_csv(master_file, index=False)

    return json_response(
        {"message": f"Deleted {deleted_count} rows", "remaining": len(df)},
        request=req,
    )
