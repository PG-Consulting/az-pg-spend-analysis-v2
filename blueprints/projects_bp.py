"""Blueprint for project and sector management endpoints."""
import logging
import azure.functions as func
from src.utils import get_models_dir
from src.api_helpers import json_response, error_response, handle_errors
from src.exceptions import NotFoundError, ConflictError, ValidationError
from src.project_manager import (
    list_sectors, create_sector, update_sector, delete_sector,
    list_projects, get_project, create_project, update_project, delete_project,
    resolve_hierarchy, resolve_hierarchy_from_body,
)

logger = logging.getLogger(__name__)
projects_bp = func.Blueprint()


@projects_bp.route(route="ListSectors", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("ListSectors")
def list_sectors_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/ListSectors - List all sectors"""
    models_dir = get_models_dir()
    sectors = list_sectors(models_dir)
    return json_response(sectors)


@projects_bp.route(route="CreateSector", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("CreateSector")
def create_sector_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/CreateSector - Create a new sector
    Body: {name: str, display_name: str, custom_hierarchy?: list}
    """
    body = req.get_json()
    name = body.get("name", "").strip().lower()
    display_name = body.get("display_name", "").strip()
    hierarchy = body.get("custom_hierarchy")
    if not name or not display_name:
        raise ValidationError("name and display_name are required")
    models_dir = get_models_dir()
    sector = create_sector(name, display_name, hierarchy, models_dir)
    return json_response(sector, 201)


@projects_bp.route(route="UpdateSector", methods=["PUT"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("UpdateSector")
def update_sector_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """PUT /api/UpdateSector - Update sector
    Body: {name: str, display_name?: str, custom_hierarchy?: list|null}
    """
    body = req.get_json()
    name = body.get("name", "").strip().lower()
    if not name:
        raise ValidationError("name is required")
    models_dir = get_models_dir()
    sector = update_sector(name, body, models_dir)
    return json_response(sector)


@projects_bp.route(route="DeleteSector", methods=["DELETE"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("DeleteSector")
def delete_sector_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """DELETE /api/DeleteSector?sectorName=xxx&force=false"""
    sector_name = req.params.get("sectorName", "").strip()
    if not sector_name:
        raise ValidationError("sectorName is required")
    force = req.params.get("force", "false").lower() == "true"
    models_dir = get_models_dir()
    try:
        result = delete_sector(sector_name, models_dir, force=force)
    except ValueError as e:
        raise ConflictError(str(e))
    if not result:
        raise NotFoundError("Sector", sector_name)
    return json_response({"success": True, **result})


@projects_bp.route(route="ListProjects", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("ListProjects")
def list_projects_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/ListProjects - List all projects"""
    models_dir = get_models_dir()
    projects = list_projects(models_dir)
    return json_response(projects)


@projects_bp.route(route="CreateProject", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("CreateProject")
def create_project_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/CreateProject
    Body: {display_name, sector, client_context?, custom_hierarchy?, hierarchy_file_base64?,
           hierarchy_filename?, hierarchy_source?}
    """
    body = req.get_json()
    resolve_hierarchy_from_body(body)
    models_dir = get_models_dir()
    project = create_project(body, models_dir)
    return json_response(project, 201)


@projects_bp.route(route="UpdateProject", methods=["PUT"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("UpdateProject")
def update_project_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """PUT /api/UpdateProject
    Body: {project_id, display_name?, client_context?, custom_hierarchy?, hierarchy_file_base64?, ...}
    """
    body = req.get_json()
    project_id = body.get("project_id", "").strip()
    if not project_id:
        raise ValidationError("project_id is required")
    resolve_hierarchy_from_body(body)
    models_dir = get_models_dir()
    project = update_project(project_id, body, models_dir)
    return json_response(project)


@projects_bp.route(route="DeleteProject", methods=["DELETE"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("DeleteProject")
def delete_project_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """DELETE /api/DeleteProject?projectId=xxx"""
    project_id = req.params.get("projectId", "").strip()
    if not project_id:
        raise ValidationError("projectId is required")
    models_dir = get_models_dir()
    success = delete_project(project_id, models_dir)
    if not success:
        raise NotFoundError("Project", project_id)
    return json_response({"success": True})


@projects_bp.route(route="GetProjectHierarchy", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("GetProjectHierarchy")
def get_project_hierarchy_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetProjectHierarchy?projectId=xxx"""
    project_id = req.params.get("projectId", "").strip()
    if not project_id:
        raise ValidationError("projectId is required")
    models_dir = get_models_dir()
    hierarchy, source = resolve_hierarchy(project_id, models_dir)
    return json_response({
        "project_id": project_id,
        "hierarchy": hierarchy,
        "source": source,
        "has_hierarchy": hierarchy is not None
    })
