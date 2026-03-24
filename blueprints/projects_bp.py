"""Blueprint for project and sector management endpoints."""

import logging
import azure.functions as func
from src.utils import get_models_dir
from src.api_helpers import json_response, options_response, handle_errors
from src.exceptions import NotFoundError, ConflictError, ValidationError
from src.validation import safe_resource_id
from src.auth import require_auth, require_admin
from src.project_manager import (
    list_sectors,
    create_sector,
    update_sector,
    delete_sector,
    list_projects,
    create_project,
    update_project,
    delete_project,
    resolve_hierarchy,
    resolve_hierarchy_from_body,
)

logger = logging.getLogger(__name__)
projects_bp = func.Blueprint()


@projects_bp.route(
    route="ListSectors", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS
)
@handle_errors("ListSectors")
@require_auth
def list_sectors_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/ListSectors - List all sectors"""
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")
    models_dir = get_models_dir()
    sectors = list_sectors(models_dir)
    return json_response(sectors, request=req)


@projects_bp.route(
    route="CreateSector",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("CreateSector")
@require_auth
def create_sector_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/CreateSector - Create a new sector
    Body: {name: str, display_name: str, custom_hierarchy?: list}
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")
    body = req.get_json()
    name = body.get("name", "").strip().lower()
    display_name = body.get("display_name", "").strip()
    hierarchy = body.get("custom_hierarchy")
    if not name or not display_name:
        raise ValidationError("name and display_name are required")
    models_dir = get_models_dir()
    sector = create_sector(name, display_name, hierarchy, models_dir)
    return json_response(sector, 201, request=req)


@projects_bp.route(
    route="UpdateSector",
    methods=["PUT", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("UpdateSector")
@require_admin
def update_sector_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """PUT /api/UpdateSector - Update sector
    Body: {name: str, display_name?: str, custom_hierarchy?: list|null}
    """
    if req.method == "OPTIONS":
        return options_response(req, "PUT, OPTIONS")
    body = req.get_json()
    name = body.get("name", "").strip().lower()
    if not name:
        raise ValidationError("name is required")
    models_dir = get_models_dir()
    sector = update_sector(name, body, models_dir)
    return json_response(sector, request=req)


@projects_bp.route(
    route="DeleteSector",
    methods=["DELETE", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("DeleteSector")
@require_admin
def delete_sector_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """DELETE /api/DeleteSector?sectorName=xxx&force=false"""
    if req.method == "OPTIONS":
        return options_response(req, "DELETE, OPTIONS")
    sector_name = safe_resource_id(req.params.get("sectorName", ""), field="sectorName")
    force = req.params.get("force", "false").lower() == "true"
    models_dir = get_models_dir()
    try:
        result = delete_sector(sector_name, models_dir, force=force)
    except ValueError as e:
        raise ConflictError(str(e))
    if not result:
        raise NotFoundError("Sector", sector_name)
    return json_response({"success": True, **result}, request=req)


@projects_bp.route(
    route="ListProjects",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("ListProjects")
@require_auth
def list_projects_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/ListProjects - List all projects"""
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")
    models_dir = get_models_dir()
    projects = list_projects(models_dir)
    return json_response(projects, request=req)


@projects_bp.route(
    route="CreateProject",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("CreateProject")
@require_auth
def create_project_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/CreateProject
    Body: {display_name, sector, client_context?, custom_hierarchy?, hierarchy_file_base64?,
           hierarchy_filename?, hierarchy_source?}
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")
    body = req.get_json()
    resolve_hierarchy_from_body(body)
    models_dir = get_models_dir()
    project = create_project(body, models_dir)
    return json_response(project, 201, request=req)


@projects_bp.route(
    route="UpdateProject",
    methods=["PUT", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("UpdateProject")
@require_auth
def update_project_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """PUT /api/UpdateProject
    Body: {project_id, display_name?, client_context?, custom_hierarchy?, hierarchy_file_base64?, ...}
    """
    if req.method == "OPTIONS":
        return options_response(req, "PUT, OPTIONS")
    body = req.get_json()
    project_id = safe_resource_id(body.get("project_id", ""), field="projectId")
    resolve_hierarchy_from_body(body)
    models_dir = get_models_dir()
    project = update_project(project_id, body, models_dir)
    return json_response(project, request=req)


@projects_bp.route(
    route="DeleteProject",
    methods=["DELETE", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("DeleteProject")
@require_auth
def delete_project_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """DELETE /api/DeleteProject?projectId=xxx"""
    if req.method == "OPTIONS":
        return options_response(req, "DELETE, OPTIONS")
    project_id = safe_resource_id(req.params.get("projectId", ""), field="projectId")
    models_dir = get_models_dir()
    success = delete_project(project_id, models_dir)
    if not success:
        raise NotFoundError("Project", project_id)
    return json_response({"success": True}, request=req)


@projects_bp.route(
    route="GetProjectHierarchy",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetProjectHierarchy")
@require_auth
def get_project_hierarchy_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetProjectHierarchy?projectId=xxx"""
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")
    project_id = safe_resource_id(req.params.get("projectId", ""), field="projectId")
    models_dir = get_models_dir()
    hierarchy, source = resolve_hierarchy(project_id, models_dir)
    return json_response(
        {
            "project_id": project_id,
            "hierarchy": hierarchy,
            "source": source,
            "has_hierarchy": hierarchy is not None,
        },
        request=req,
    )
