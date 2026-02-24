"""CRUD operations for sectors and projects stored as JSON files on disk."""
import os
import json
import re
import shutil
import logging
from datetime import datetime, timezone
from typing import Optional

from src.utils import get_models_dir, get_sectors_dir, get_projects_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert display_name to a safe lowercase slug for use as folder names."""
    text = text.lower().strip()
    # Replace accented/special characters with ASCII equivalents via encode round-trip
    import unicodedata
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    # Replace non-alphanumeric characters with hyphens
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _extract_n4s(hierarchy: list) -> set:
    """Extract all unique N4 values from hierarchy list."""
    return {entry.get("N4", "").strip() for entry in hierarchy if entry.get("N4")}


def _read_json(path: str) -> Optional[dict]:
    """Read a JSON file and return its contents, or None if it does not exist."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read JSON at {path}: {e}")
        return None


def _write_json(path: str, data: dict) -> None:
    """Write data to a JSON file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Sector CRUD
# ---------------------------------------------------------------------------

def list_sectors(models_dir: str) -> list:
    """List all sectors from sectors/ subdirectories."""
    sectors_dir = os.path.join(models_dir, "sectors")
    if not os.path.isdir(sectors_dir):
        return []
    result = []
    for entry in sorted(os.listdir(sectors_dir)):
        config_path = os.path.join(sectors_dir, entry, "sector_config.json")
        config = _read_json(config_path)
        if config:
            result.append(config)
    return result


def get_sector(name: str, models_dir: str) -> Optional[dict]:
    """Get single sector config or None if not found."""
    config_path = os.path.join(models_dir, "sectors", name.lower(), "sector_config.json")
    return _read_json(config_path)


def create_sector(name: str, display_name: str, hierarchy: Optional[list], models_dir: str) -> dict:
    """Create a new sector. name is lowercased and used as folder name."""
    name = name.lower().strip()
    sector_dir = os.path.join(models_dir, "sectors", name)
    os.makedirs(sector_dir, exist_ok=True)

    config = {
        "name": name,
        "display_name": display_name,
        "custom_hierarchy": hierarchy,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    config_path = os.path.join(sector_dir, "sector_config.json")
    _write_json(config_path, config)
    logger.info(f"Sector '{name}' created at {sector_dir}")
    return config


def update_sector(name: str, data: dict, models_dir: str) -> dict:
    """Update existing sector config."""
    name = name.lower().strip()
    config_path = os.path.join(models_dir, "sectors", name, "sector_config.json")
    existing = _read_json(config_path)
    if existing is None:
        raise FileNotFoundError(f"Sector '{name}' not found")

    # Merge: only update fields provided in data
    for key, value in data.items():
        if key != "name":  # name/folder is immutable
            existing[key] = value

    _write_json(config_path, existing)
    logger.info(f"Sector '{name}' updated")
    return existing


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------

def list_projects(models_dir: str) -> list:
    """List all projects from projects/ subdirectories."""
    projects_dir = os.path.join(models_dir, "projects")
    if not os.path.isdir(projects_dir):
        return []
    result = []
    for entry in sorted(os.listdir(projects_dir)):
        config_path = os.path.join(projects_dir, entry, "project_config.json")
        config = _read_json(config_path)
        if config:
            result.append(config)
    return result


def get_project(project_id: str, models_dir: str) -> Optional[dict]:
    """Get single project config or None if not found."""
    config_path = os.path.join(models_dir, "projects", project_id, "project_config.json")
    return _read_json(config_path)


def create_project(data: dict, models_dir: str) -> dict:
    """Create a new project.

    data fields:
        display_name (required): Human-readable name, e.g. "Naval - WARTISLA"
        sector (required): Sector name, e.g. "naval"
        client_context (optional): Free-text context for LLM prompts
        custom_hierarchy (optional): list of {N1,N2,N3,N4} dicts or None
        hierarchy_source (optional): "own" | "inherited" | "padrao" (default "own")
        hierarchy_filename (optional): Original filename of uploaded hierarchy
        few_shot_max_examples (optional): int, default 5

    Auto-generates project_id from display_name (slugified, lowercase, hyphenated).
    Creates directory structure: models_dir/projects/{project_id}/
    Also creates empty knowledge_base.json: []
    """
    display_name = data.get("display_name", "").strip()
    if not display_name:
        raise ValueError("display_name is required")

    sector = data.get("sector", "").strip().lower()
    if not sector:
        raise ValueError("sector is required")

    project_id = _slugify(display_name)
    if not project_id:
        raise ValueError(f"Could not generate a valid project_id from display_name '{display_name}'")

    project_dir = os.path.join(models_dir, "projects", project_id)
    os.makedirs(project_dir, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    config = {
        "project_id": project_id,
        "display_name": display_name,
        "sector": sector,
        "client_context": data.get("client_context", ""),
        "custom_hierarchy": data.get("custom_hierarchy", None),
        "hierarchy_source": data.get("hierarchy_source", "own"),
        "hierarchy_filename": data.get("hierarchy_filename", None),
        "created_at": now,
        "updated_at": now,
        "few_shot_max_examples": int(data.get("few_shot_max_examples", 5)),
        "use_sector_kb": bool(data.get("use_sector_kb", True)),
    }

    config_path = os.path.join(project_dir, "project_config.json")
    _write_json(config_path, config)

    # Create empty knowledge_base.json
    kb_path = os.path.join(project_dir, "knowledge_base.json")
    if not os.path.exists(kb_path):
        with open(kb_path, "w", encoding="utf-8") as f:
            json.dump([], f)

    logger.info(f"Project '{project_id}' created at {project_dir}")
    return config


def update_project(project_id: str, data: dict, models_dir: str) -> dict:
    """Update existing project config. Updates updated_at timestamp."""
    config_path = os.path.join(models_dir, "projects", project_id, "project_config.json")
    existing = _read_json(config_path)
    if existing is None:
        raise FileNotFoundError(f"Project '{project_id}' not found")

    # Immutable fields
    immutable = {"project_id", "created_at"}
    for key, value in data.items():
        if key not in immutable:
            existing[key] = value

    existing["updated_at"] = datetime.now(timezone.utc).isoformat()

    _write_json(config_path, existing)
    logger.info(f"Project '{project_id}' updated")
    return existing


def delete_project(project_id: str, models_dir: str) -> bool:
    """Delete project directory and all contents. Returns False if not found."""
    project_dir = os.path.join(models_dir, "projects", project_id)
    if not os.path.isdir(project_dir):
        logger.warning(f"Project '{project_id}' not found for deletion")
        return False
    shutil.rmtree(project_dir)
    logger.info(f"Project '{project_id}' deleted")
    return True


# ---------------------------------------------------------------------------
# Hierarchy resolution
# ---------------------------------------------------------------------------

def resolve_hierarchy(project_id: str, models_dir: str) -> tuple:
    """Returns (hierarchy: list|None, source: str) following precedence:
    1. Project's own custom_hierarchy -> source="own"
    2. Project's sector custom_hierarchy -> source="inherited"
    3. No hierarchy -> source="padrao", return None
    """
    project = get_project(project_id, models_dir)
    if project is None:
        raise FileNotFoundError(f"Project '{project_id}' not found")

    # 1. Project's own hierarchy
    own = project.get("custom_hierarchy")
    if own:
        return own, "own"

    # 2. Sector hierarchy
    sector_name = project.get("sector", "")
    if sector_name:
        sector = get_sector(sector_name, models_dir)
        if sector:
            sector_hierarchy = sector.get("custom_hierarchy")
            if sector_hierarchy:
                return sector_hierarchy, "inherited"

    # 3. Fallback: no hierarchy
    return None, "padrao"


