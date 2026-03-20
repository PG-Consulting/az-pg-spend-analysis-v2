"""Blueprint for Knowledge Base management endpoints."""

import base64
import logging

import azure.functions as func
from src.api_helpers import (
    json_response,
    options_response,
    handle_errors,
)
from src.exceptions import NotFoundError, ValidationError
from src.utils import get_models_dir
from src.knowledge_base import KnowledgeBase, merge_kb_entries
from src.auth import require_auth, require_admin

logger = logging.getLogger(__name__)
knowledge_bp = func.Blueprint()


def _get_project_id(req: func.HttpRequest) -> str:
    """Extract and validate projectId from query params."""
    return req.params.get("projectId", "").strip()


@knowledge_bp.route(
    route="GetKnowledgeBase",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetKnowledgeBase")
@require_auth
def get_knowledge_base_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetKnowledgeBase?projectId=xxx&page=1&pageSize=50&source=...&n4=...&search=...
    Returns paginated KB entries for a project.
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    project_id = _get_project_id(req)
    if not project_id:
        raise ValidationError("projectId is required")

    page = int(req.params.get("page", 1))
    page_size = min(int(req.params.get("pageSize", 50)), 200)
    source_filter = req.params.get("source", "").strip() or None
    n4_filter = req.params.get("n4", "").strip() or None
    search_filter = req.params.get("search", "").strip() or None

    models_dir = get_models_dir()
    kb = KnowledgeBase(project_id, models_dir)

    filters = {}
    if source_filter:
        filters["source"] = source_filter
    if n4_filter:
        filters["n4"] = n4_filter
    if search_filter:
        filters["search_query"] = search_filter

    result = kb.get_all(
        page=page, page_size=page_size, filters=filters if filters else None
    )

    return json_response(result)


@knowledge_bp.route(
    route="AddKBEntry", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS
)
@handle_errors("AddKBEntry")
@require_auth
def add_kb_entry_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/AddKBEntry
    Body: {projectId, description, N1, N2, N3, N4, source?, confidence?}
    Adds a single manual entry to the project KB.
    Returns: {success, entry_count}
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    body = req.get_json()
    project_id = body.get("projectId", "").strip()
    if not project_id:
        raise ValidationError("projectId is required")

    description = body.get("description", "").strip()
    if not description:
        raise ValidationError("description is required")

    entry = {
        "description": description,
        "N1": body.get("N1", ""),
        "N2": body.get("N2", ""),
        "N3": body.get("N3", ""),
        "N4": body.get("N4", ""),
        "source": body.get("source", "consultant_correction"),
        "confidence": float(body.get("confidence", 1.0)),
        "instruction_used": body.get("instruction_used"),
    }

    models_dir = get_models_dir()
    kb = KnowledgeBase(project_id, models_dir)
    added = kb.add_entries([entry])

    return json_response(
        {"success": True, "added": added, "entry_count": len(kb.entries)},
        status_code=201,
    )


@knowledge_bp.route(
    route="UpdateKBEntry",
    methods=["PUT", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("UpdateKBEntry")
@require_auth
def update_kb_entry_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """PUT /api/UpdateKBEntry
    Body: {projectId, entryId, description?, N1?, N2?, N3?, N4?}
    Updates an existing KB entry by ID.
    Returns: {success}
    """
    if req.method == "OPTIONS":
        return options_response(req, "PUT, OPTIONS")

    body = req.get_json()
    project_id = body.get("projectId", "").strip()
    entry_id = body.get("entryId", "").strip()
    if not project_id or not entry_id:
        raise ValidationError("projectId and entryId are required")

    # Build update payload from provided fields
    update_data = {}
    for field in (
        "description",
        "N1",
        "N2",
        "N3",
        "N4",
        "source",
        "confidence",
        "instruction_used",
    ):
        if field in body:
            update_data[field] = body[field]

    if not update_data:
        raise ValidationError("No fields to update provided")

    models_dir = get_models_dir()
    kb = KnowledgeBase(project_id, models_dir)
    success = kb.update_entry(entry_id, update_data)

    if not success:
        raise NotFoundError("Entry", entry_id)

    return json_response({"success": True})


@knowledge_bp.route(
    route="DeleteKBEntry",
    methods=["DELETE", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("DeleteKBEntry")
@require_auth
def delete_kb_entry_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """DELETE /api/DeleteKBEntry?projectId=xxx&entryId=xxx
    Deletes a single KB entry by ID.
    Returns: {success}
    """
    if req.method == "OPTIONS":
        return options_response(req, "DELETE, OPTIONS")

    project_id = req.params.get("projectId", "").strip()
    entry_id = req.params.get("entryId", "").strip()
    if not project_id or not entry_id:
        raise ValidationError("projectId and entryId are required")

    models_dir = get_models_dir()
    kb = KnowledgeBase(project_id, models_dir)
    success = kb.delete_entry(entry_id)

    if not success:
        raise NotFoundError("Entry", entry_id)

    return json_response({"success": True})


@knowledge_bp.route(
    route="GetKBCoverage",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetKBCoverage")
@require_auth
def get_kb_coverage_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetKBCoverage?projectId=xxx
    Returns KB coverage against the project's resolved hierarchy.
    Includes merged breakdown: project_entries, sector_entries, merged_entries.
    Returns: {total_n4s, covered, pct, underserved, project_entries, sector_entries, merged_entries}
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    project_id = _get_project_id(req)
    if not project_id:
        raise ValidationError("projectId is required")

    models_dir = get_models_dir()

    # Resolve project hierarchy (own > inherited > padrao)
    from src.project_manager import resolve_hierarchy, get_project

    hierarchy, source = resolve_hierarchy(project_id, models_dir)

    # Load project KB
    project_kb = KnowledgeBase(project_id, models_dir)
    project_entry_count = len(project_kb.entries)

    # Load sector KB (only if use_sector_kb is enabled)
    project_config = get_project(project_id, models_dir)
    sector_slug = project_config.get("sector", "") if project_config else ""
    use_sector_kb = (
        project_config.get("use_sector_kb", True) if project_config else True
    )
    sector_entry_count = 0
    if sector_slug and use_sector_kb:
        try:
            sector_kb = KnowledgeBase(sector_slug, models_dir, entity_type="sector")
            sector_entry_count = len(sector_kb.entries)
            merged = merge_kb_entries(sector_kb.entries, project_kb.entries)
        except Exception:
            merged = project_kb.entries
    else:
        merged = project_kb.entries

    # Calculate coverage with merged entries using a temporary instance
    # (avoids mutating project_kb.entries, which is thread-unsafe)
    temp_kb = KnowledgeBase.__new__(KnowledgeBase)
    temp_kb.entries = merged
    coverage = temp_kb.get_coverage(hierarchy)

    coverage["hierarchy_source"] = source
    coverage["project_entries"] = project_entry_count
    coverage["sector_entries"] = sector_entry_count
    coverage["merged_entries"] = len(merged)

    return json_response(coverage)


@knowledge_bp.route(
    route="GetKBVersions",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetKBVersions")
@require_auth
def get_kb_versions_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetKBVersions?projectId=xxx
    Returns a list of KB version snapshots for a project.
    Returns: [{version_id, created_at, entry_count}]
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    project_id = _get_project_id(req)
    if not project_id:
        raise ValidationError("projectId is required")

    models_dir = get_models_dir()
    kb = KnowledgeBase(project_id, models_dir)
    versions = kb.list_versions()

    return json_response(versions)


@knowledge_bp.route(
    route="RollbackKB", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS
)
@handle_errors("RollbackKB")
@require_auth
def rollback_kb_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/RollbackKB
    Body: {projectId, versionId}
    Rolls back the KB to a previously saved snapshot.
    Returns: {success, entry_count}
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    body = req.get_json()
    project_id = body.get("projectId", "").strip()
    version_id = body.get("versionId", "").strip()
    if not project_id or not version_id:
        raise ValidationError("projectId and versionId are required")

    models_dir = get_models_dir()
    kb = KnowledgeBase(project_id, models_dir)
    success = kb.rollback_to_version(version_id)

    if not success:
        raise NotFoundError("Version", version_id)

    return json_response({"success": True, "entry_count": len(kb.entries)})


@knowledge_bp.route(
    route="ExportKB", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS
)
@handle_errors("ExportKB")
@require_auth
def export_kb_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/ExportKB?projectId=xxx
    Exports all KB entries as a base64-encoded XLSX file.
    Returns: {projectId, entry_count, filename, file_content_base64}
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    project_id = _get_project_id(req)
    if not project_id:
        raise ValidationError("projectId is required")

    models_dir = get_models_dir()
    kb = KnowledgeBase(project_id, models_dir)
    xlsx_bytes = kb.export_xlsx()
    file_b64 = base64.b64encode(xlsx_bytes).decode("utf-8")

    return json_response(
        {
            "projectId": project_id,
            "entry_count": len(kb.entries),
            "filename": f"knowledge_base_{project_id}.xlsx",
            "file_content_base64": file_b64,
        }
    )


@knowledge_bp.route(
    route="ImportKB", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS
)
@handle_errors("ImportKB")
@require_auth
def import_kb_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/ImportKB
    Body: {projectId, fileContentBase64}
    Imports KB entries from a base64-encoded XLSX file (format exported by ExportKB).
    Deduplicates by (description_norm, N4).
    Returns: {success, added, total}
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    body = req.get_json()
    project_id = body.get("projectId", "").strip()
    file_content_b64 = body.get("fileContentBase64", "").strip()

    if not project_id:
        raise ValidationError("projectId is required")
    if not file_content_b64:
        raise ValidationError("fileContentBase64 is required")

    file_bytes = base64.b64decode(file_content_b64)

    models_dir = get_models_dir()
    kb = KnowledgeBase(project_id, models_dir)
    kb.create_version_snapshot()  # snapshot before import
    result = kb.import_xlsx(file_bytes)

    return json_response(
        {"success": True, "added": result["added"], "total": result["total"]}
    )


# ===========================================================================
# Sector KB endpoints
# ===========================================================================


def _get_sector_name(req: func.HttpRequest) -> str:
    """Extract and validate sectorName from query params."""
    return req.params.get("sectorName", "").strip().lower()


@knowledge_bp.route(
    route="GetSectorKB", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS
)
@handle_errors("GetSectorKB")
@require_auth
def get_sector_kb_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetSectorKB?sectorName=xxx&page=1&pageSize=50&search=...
    Returns paginated KB entries for a sector.
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    sector_name = _get_sector_name(req)
    if not sector_name:
        raise ValidationError("sectorName is required")

    page = int(req.params.get("page", 1))
    page_size = min(int(req.params.get("pageSize", 50)), 200)
    search_filter = req.params.get("search", "").strip() or None

    models_dir = get_models_dir()
    kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")

    filters = {}
    if search_filter:
        filters["search_query"] = search_filter

    result = kb.get_all(
        page=page, page_size=page_size, filters=filters if filters else None
    )

    return json_response(result)


@knowledge_bp.route(
    route="GetSectorKBCoverage",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetSectorKBCoverage")
@require_auth
def get_sector_kb_coverage_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetSectorKBCoverage?sectorName=xxx
    Returns KB coverage for a sector against its hierarchy.
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    sector_name = _get_sector_name(req)
    if not sector_name:
        raise ValidationError("sectorName is required")

    models_dir = get_models_dir()

    from src.project_manager import get_sector

    sector = get_sector(sector_name, models_dir)
    hierarchy = sector.get("custom_hierarchy") if sector else None

    kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")
    coverage = kb.get_coverage(hierarchy)

    return json_response(coverage)


@knowledge_bp.route(
    route="GetSectorKBVersions",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetSectorKBVersions")
@require_auth
def get_sector_kb_versions_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetSectorKBVersions?sectorName=xxx
    Returns a list of KB version snapshots for a sector.
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    sector_name = _get_sector_name(req)
    if not sector_name:
        raise ValidationError("sectorName is required")

    models_dir = get_models_dir()
    kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")
    versions = kb.list_versions()

    return json_response(versions)


@knowledge_bp.route(
    route="ExportSectorKB",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("ExportSectorKB")
@require_auth
def export_sector_kb_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/ExportSectorKB?sectorName=xxx
    Exports all sector KB entries as a base64-encoded XLSX file.
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    sector_name = _get_sector_name(req)
    if not sector_name:
        raise ValidationError("sectorName is required")

    models_dir = get_models_dir()
    kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")
    xlsx_bytes = kb.export_xlsx()
    file_b64 = base64.b64encode(xlsx_bytes).decode("utf-8")

    return json_response(
        {
            "sectorName": sector_name,
            "entry_count": len(kb.entries),
            "filename": f"knowledge_base_sector_{sector_name}.xlsx",
            "file_content_base64": file_b64,
        }
    )


@knowledge_bp.route(
    route="ImportSectorKB",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("ImportSectorKB")
@require_admin
def import_sector_kb_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/ImportSectorKB
    Body: {sectorName, fileContentBase64}
    Imports KB entries from a base64-encoded XLSX file into the sector KB.
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    body = req.get_json()
    sector_name = body.get("sectorName", "").strip().lower()
    file_content_b64 = body.get("fileContentBase64", "").strip()

    if not sector_name:
        raise ValidationError("sectorName is required")
    if not file_content_b64:
        raise ValidationError("fileContentBase64 is required")

    file_bytes = base64.b64decode(file_content_b64)

    models_dir = get_models_dir()
    kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")
    kb.create_version_snapshot()
    result = kb.import_xlsx(file_bytes)

    return json_response(
        {"success": True, "added": result["added"], "total": result["total"]}
    )


@knowledge_bp.route(
    route="UpdateSectorKBEntry",
    methods=["PUT", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("UpdateSectorKBEntry")
@require_admin
def update_sector_kb_entry_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """PUT /api/UpdateSectorKBEntry
    Body: {sectorName, entryId, description?, N1?, N2?, N3?, N4?}
    Updates an existing sector KB entry by ID.
    Returns: {success}
    """
    if req.method == "OPTIONS":
        return options_response(req, "PUT, OPTIONS")

    body = req.get_json()
    sector_name = body.get("sectorName", "").strip().lower()
    entry_id = body.get("entryId", "").strip()
    if not sector_name or not entry_id:
        raise ValidationError("sectorName and entryId are required")

    update_data = {}
    for field in (
        "description",
        "N1",
        "N2",
        "N3",
        "N4",
        "source",
        "confidence",
        "instruction_used",
    ):
        if field in body:
            update_data[field] = body[field]

    if not update_data:
        raise ValidationError("No fields to update provided")

    models_dir = get_models_dir()
    kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")
    success = kb.update_entry(entry_id, update_data)

    if not success:
        raise NotFoundError("Entry", entry_id)

    return json_response({"success": True})


@knowledge_bp.route(
    route="DeleteSectorKBEntry",
    methods=["DELETE", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("DeleteSectorKBEntry")
@require_admin
def delete_sector_kb_entry_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """DELETE /api/DeleteSectorKBEntry?sectorName=x&entryId=y
    Deletes a single sector KB entry by ID.
    Returns: {success}
    """
    if req.method == "OPTIONS":
        return options_response(req, "DELETE, OPTIONS")

    sector_name = req.params.get("sectorName", "").strip().lower()
    entry_id = req.params.get("entryId", "").strip()
    if not sector_name or not entry_id:
        raise ValidationError("sectorName and entryId are required")

    models_dir = get_models_dir()
    kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")
    success = kb.delete_entry(entry_id)

    if not success:
        raise NotFoundError("Entry", entry_id)

    return json_response({"success": True})


@knowledge_bp.route(
    route="RollbackSectorKB",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("RollbackSectorKB")
@require_admin
def rollback_sector_kb_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/RollbackSectorKB
    Body: {sectorName, versionId}
    Rolls back the sector KB to a previously saved snapshot.
    Returns: {success, entry_count}
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    body = req.get_json()
    sector_name = body.get("sectorName", "").strip().lower()
    version_id = body.get("versionId", "").strip()
    if not sector_name or not version_id:
        raise ValidationError("sectorName and versionId are required")

    models_dir = get_models_dir()
    kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")
    success = kb.rollback_to_version(version_id)

    if not success:
        raise NotFoundError("Version", version_id)

    return json_response({"success": True, "entry_count": len(kb.entries)})


@knowledge_bp.route(
    route="AddSectorKBEntry",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("AddSectorKBEntry")
@require_admin
def add_sector_kb_entry_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/AddSectorKBEntry
    Body: {sectorName, description, N1, N2, N3, N4, source?, confidence?}
    Adds a single manual entry to the sector KB.
    Returns: {success, entry_count}
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    body = req.get_json()
    sector_name = body.get("sectorName", "").strip().lower()
    if not sector_name:
        raise ValidationError("sectorName is required")

    description = body.get("description", "").strip()
    if not description:
        raise ValidationError("description is required")

    entry = {
        "description": description,
        "N1": body.get("N1", ""),
        "N2": body.get("N2", ""),
        "N3": body.get("N3", ""),
        "N4": body.get("N4", ""),
        "source": body.get("source", "consultant_correction"),
        "confidence": float(body.get("confidence", 1.0)),
        "instruction_used": body.get("instruction_used"),
    }

    models_dir = get_models_dir()
    kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")
    added = kb.add_entries([entry])

    return json_response(
        {"success": True, "added": added, "entry_count": len(kb.entries)},
        status_code=201,
    )


@knowledge_bp.route(
    route="PromoteToSectorKB",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("PromoteToSectorKB")
@require_admin
def promote_to_sector_kb_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/PromoteToSectorKB
    Body: {projectId, sectorName, entryIds: [str]}
    Promotes selected entries from a project KB to the sector KB.
    Returns: {success, promoted_count}
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    body = req.get_json()
    project_id = body.get("projectId", "").strip()
    sector_name = body.get("sectorName", "").strip().lower()
    entry_ids = body.get("entryIds", [])

    if not project_id:
        raise ValidationError("projectId is required")
    if not sector_name:
        raise ValidationError("sectorName is required")
    if not entry_ids:
        raise ValidationError("entryIds must not be empty")

    models_dir = get_models_dir()
    project_kb = KnowledgeBase(project_id, models_dir)
    sector_kb = KnowledgeBase(sector_name, models_dir, entity_type="sector")

    promoted = project_kb.promote_entries_to(sector_kb, entry_ids)

    return json_response({"success": True, "promoted_count": promoted})
