"""CRUD operations for sectors and projects stored as JSON files on disk."""

import os
import io
import json
import re
import base64
import shutil
import logging
from datetime import datetime, timezone
from typing import Optional, List


logger = logging.getLogger(__name__)

_CONFIG_LOCK_TIMEOUT = 10  # seconds


def _config_lock(config_path: str):
    """Create a FileLock for a config JSON file."""
    import filelock

    return filelock.FileLock(config_path + ".lock", timeout=_CONFIG_LOCK_TIMEOUT)


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
    config_path = os.path.join(
        models_dir, "sectors", name.lower(), "sector_config.json"
    )
    return _read_json(config_path)


def create_sector(
    name: str, display_name: str, hierarchy: Optional[list], models_dir: str
) -> dict:
    """Create a new sector. name is lowercased and used as folder name.

    Note: hierarchy parameter is accepted for backwards compatibility but ignored.
    Sectors only have a knowledge base, not a hierarchy.
    """
    name = name.lower().strip()
    sector_dir = os.path.join(models_dir, "sectors", name)
    os.makedirs(sector_dir, exist_ok=True)

    config = {
        "name": name,
        "display_name": display_name,
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
    lock = _config_lock(config_path)
    with lock:
        existing = _read_json(config_path)
        if existing is None:
            raise FileNotFoundError(f"Sector '{name}' not found")
        for key, value in data.items():
            if key != "name":
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
    config_path = os.path.join(
        models_dir, "projects", project_id, "project_config.json"
    )
    return _read_json(config_path)


def create_project(data: dict, models_dir: str) -> dict:
    """Create a new project.

    data fields:
        display_name (required): Human-readable name, e.g. "Naval - WARTISLA"
        sector (required): Sector name, e.g. "naval"
        client_context (optional): Free-text context for LLM prompts
        custom_hierarchy (optional): list of {N1,N2,N3,N4} dicts or None
        hierarchy_source (optional): "own" | "padrao" (default "own")
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
        raise ValueError(
            f"Could not generate a valid project_id from display_name '{display_name}'"
        )

    project_dir = os.path.join(models_dir, "projects", project_id)
    os.makedirs(project_dir, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    config = {
        "project_id": project_id,
        "display_name": display_name,
        "sector": sector,
        "client_context": data.get("client_context", ""),
        "custom_hierarchy": data.get("custom_hierarchy", None),
        "hierarchy_source": data.get("hierarchy_source", "padrao"),
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
    config_path = os.path.join(
        models_dir, "projects", project_id, "project_config.json"
    )
    lock = _config_lock(config_path)
    with lock:
        existing = _read_json(config_path)
        if existing is None:
            raise FileNotFoundError(f"Project '{project_id}' not found")
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


def delete_sector(name: str, models_dir: str, force: bool = False) -> dict:
    """Delete sector directory and all contents.

    If force=False and projects exist for this sector, raises ValueError.
    If force=True, deletes all projects of the sector first, then the sector.

    Returns: {"deleted_sector": name, "deleted_projects": [...]}
    Returns empty dict if sector not found.
    """
    name = name.lower().strip()
    sector_dir = os.path.join(models_dir, "sectors", name)
    if not os.path.isdir(sector_dir):
        logger.warning(f"Sector '{name}' not found for deletion")
        return {}

    # Find projects belonging to this sector
    sector_projects = [p for p in list_projects(models_dir) if p.get("sector") == name]
    deleted_project_ids = []

    if sector_projects and not force:
        project_ids = [p["project_id"] for p in sector_projects]
        raise ValueError(
            f"Setor '{name}' possui {len(sector_projects)} projeto(s): {', '.join(project_ids)}. "
            f"Use force=true para excluir o setor e todos os seus projetos."
        )

    if sector_projects and force:
        for p in sector_projects:
            pid = p["project_id"]
            delete_project(pid, models_dir)
            deleted_project_ids.append(pid)
            logger.info(f"Project '{pid}' deleted as part of sector '{name}' deletion")

    shutil.rmtree(sector_dir)
    logger.info(f"Sector '{name}' deleted")
    return {"deleted_sector": name, "deleted_projects": deleted_project_ids}


# ---------------------------------------------------------------------------
# Hierarchy parsing from base64 Excel
# ---------------------------------------------------------------------------


def parse_hierarchy_from_b64(b64_string: str) -> Optional[List[dict]]:
    """Parse a base64-encoded Excel file into a list of {N1,N2,N3,N4} dicts.

    Used when the frontend sends hierarchy_file_base64 (raw Excel) instead of
    a pre-parsed custom_hierarchy list. Detects header row automatically.
    Returns list of dicts or None on failure.
    """
    import pandas as pd

    if not b64_string:
        return None
    try:
        cust_bytes = base64.b64decode(b64_string)
        df_raw = pd.read_excel(io.BytesIO(cust_bytes), header=None)

        # Find header row containing N1 and N4
        header_row = None
        for idx, row in df_raw.iterrows():
            values = [str(v).strip().upper() for v in row.values]
            if "N1" in values and "N4" in values:
                header_row = idx
                break

        if header_row is None:
            logger.error("Hierarchy file: headers N1/N4 not found")
            return None

        df_hier = pd.read_excel(io.BytesIO(cust_bytes), header=header_row)
        df_hier.columns = [str(c).strip().upper() for c in df_hier.columns]

        if "N4" not in df_hier.columns:
            logger.error(
                f"Hierarchy file: N4 column missing. Columns: {list(df_hier.columns)}"
            )
            return None

        hierarchy: List[dict] = []
        for _, row in df_hier.iterrows():
            n4 = str(row.get("N4", "")).strip()
            if n4 and n4.upper() != "NAN":
                hierarchy.append(
                    {
                        "N1": str(row.get("N1", "")).strip()
                        if pd.notna(row.get("N1"))
                        else "",
                        "N2": str(row.get("N2", "")).strip()
                        if pd.notna(row.get("N2"))
                        else "",
                        "N3": str(row.get("N3", "")).strip()
                        if pd.notna(row.get("N3"))
                        else "",
                        "N4": n4,
                    }
                )

        logger.info(f"Hierarchy file parsed: {len(hierarchy)} entries")
        return hierarchy if hierarchy else None
    except Exception as e:
        logger.error(f"Failed to parse hierarchy file: {e}")
        return None


def resolve_hierarchy_from_body(body: dict) -> None:
    """Mutate body in-place: if hierarchy_file_base64 is present, parse it
    into custom_hierarchy and set hierarchy_source accordingly.

    Called by CreateProject/UpdateProject endpoints before saving to config.

    Priority:
      1. custom_hierarchy already provided as list → use as-is
      2. hierarchy_file_base64 (base64 Excel) → parse into custom_hierarchy
      3. Neither → ensure hierarchy_source reflects 'padrao'
    """
    # Already have a parsed hierarchy? Nothing to do
    existing = body.get("custom_hierarchy")
    if existing and isinstance(existing, list) and len(existing) > 0:
        body.setdefault("hierarchy_source", "own")
        return

    # Try parsing from base64 file
    b64 = body.pop("hierarchy_file_base64", None)
    if b64:
        parsed = parse_hierarchy_from_b64(b64)
        if parsed:
            body["custom_hierarchy"] = parsed
            body.setdefault("hierarchy_source", "own")
            logger.info(f"Hierarchy parsed from file: {len(parsed)} entries")
            return
        else:
            logger.warning("hierarchy_file_base64 provided but parsing failed")

    # No hierarchy provided — ensure source reflects reality
    if not body.get("custom_hierarchy"):
        body.setdefault("hierarchy_source", "padrao")


# ---------------------------------------------------------------------------
# Hierarchy resolution
# ---------------------------------------------------------------------------


def resolve_hierarchy(project_id: str, models_dir: str) -> tuple:
    """Returns (hierarchy: list|None, source: str) following precedence:
    1. Project's own custom_hierarchy -> source="own"
    2. No hierarchy -> source="padrao", return None
    """
    project = get_project(project_id, models_dir)
    if project is None:
        raise FileNotFoundError(f"Project '{project_id}' not found")

    # 1. Project's own hierarchy
    own = project.get("custom_hierarchy")
    if own:
        return own, "own"

    # 2. Fallback: no hierarchy
    return None, "padrao"
