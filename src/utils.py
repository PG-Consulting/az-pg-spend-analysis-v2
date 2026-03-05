"""Utility functions and constants shared across the application."""
import os
import json
import math
import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_models_dir() -> str:
    """Resolve models directory: env override -> /mount/models -> local ./models"""
    custom = os.environ.get("MODELS_DIR_PATH", "").strip()
    if custom:
        return custom
    mount_path = "/mount/models"
    if os.path.isdir(mount_path):
        return mount_path
    local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
    os.makedirs(local_path, exist_ok=True)
    return local_path


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """JSON serializer that handles NaN and Infinity by converting to None."""

    def clean_obj(inner_obj):
        if isinstance(inner_obj, dict):
            return {k: clean_obj(v) for k, v in inner_obj.items()}
        elif isinstance(inner_obj, list):
            return [clean_obj(i) for i in inner_obj]
        elif isinstance(inner_obj, float):
            if math.isnan(inner_obj) or math.isinf(inner_obj):
                return None
        return inner_obj

    return json.dumps(clean_obj(obj), ensure_ascii=False, **kwargs)


# Compute directories lazily (call get_models_dir() at function call time, not module load)
def get_sectors_dir() -> str:
    return os.path.join(get_models_dir(), "sectors")


def get_projects_dir() -> str:
    return os.path.join(get_models_dir(), "projects")


def get_jobs_dir() -> str:
    return os.path.join(get_models_dir(), "taxonomy_jobs")


# ---------------------------------------------------------------------------
# Source label mapping (internal source → friendly label for UI and Excel)
# ---------------------------------------------------------------------------

_SOURCE_LABELS = {
    "KB (Direct Match)": "Base de Aprendizado",
    "LLM (Batch)": "Grok",
    "LLM (Reclassified)": "Grok",
    "Taxonomy (Dict)": "Dicionário",
    "ML": "ML",
    "consultant_correction": "Ajuste Manual",
    "reclassified_with_guidance": "Reclassificado",
}


def friendly_source_label(source: str) -> str:
    """Map internal source identifier to a user-friendly label."""
    return _SOURCE_LABELS.get(source, source or "")


# ---------------------------------------------------------------------------
# Incomplete classification values (centralised)
# ---------------------------------------------------------------------------

INCOMPLETE_VALUES = frozenset({"", "Não Identificado", "Nao Identificado"})
