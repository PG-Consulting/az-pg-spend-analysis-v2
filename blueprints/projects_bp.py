"""Blueprint for project and sector management endpoints."""
import json
import logging
import azure.functions as func
from src.utils import get_models_dir
from src.project_manager import (
    list_sectors, create_sector, update_sector,
    list_projects, get_project, create_project, update_project, delete_project,
    resolve_hierarchy,
)

logger = logging.getLogger(__name__)
projects_bp = func.Blueprint()


@projects_bp.route(route="ListSectors", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def list_sectors_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/ListSectors - List all sectors"""
    try:
        models_dir = get_models_dir()
        sectors = list_sectors(models_dir)
        return func.HttpResponse(json.dumps(sectors, ensure_ascii=False),
                                 status_code=200, mimetype="application/json")
    except Exception as e:
        logger.error(f"ListSectors error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@projects_bp.route(route="CreateSector", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def create_sector_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/CreateSector - Create a new sector
    Body: {name: str, display_name: str, custom_hierarchy?: list}
    """
    try:
        body = req.get_json()
        name = body.get("name", "").strip().lower()
        display_name = body.get("display_name", "").strip()
        hierarchy = body.get("custom_hierarchy")
        if not name or not display_name:
            return func.HttpResponse(json.dumps({"error": "name and display_name are required"}),
                                     status_code=400, mimetype="application/json")
        models_dir = get_models_dir()
        sector = create_sector(name, display_name, hierarchy, models_dir)
        return func.HttpResponse(json.dumps(sector, ensure_ascii=False),
                                 status_code=201, mimetype="application/json")
    except Exception as e:
        logger.error(f"CreateSector error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@projects_bp.route(route="UpdateSector", methods=["PUT"], auth_level=func.AuthLevel.ANONYMOUS)
def update_sector_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """PUT /api/UpdateSector - Update sector
    Body: {name: str, display_name?: str, custom_hierarchy?: list|null}
    """
    try:
        body = req.get_json()
        name = body.get("name", "").strip().lower()
        if not name:
            return func.HttpResponse(json.dumps({"error": "name is required"}),
                                     status_code=400, mimetype="application/json")
        models_dir = get_models_dir()
        sector = update_sector(name, body, models_dir)
        return func.HttpResponse(json.dumps(sector, ensure_ascii=False),
                                 status_code=200, mimetype="application/json")
    except Exception as e:
        logger.error(f"UpdateSector error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@projects_bp.route(route="ListProjects", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def list_projects_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/ListProjects - List all projects"""
    try:
        models_dir = get_models_dir()
        projects = list_projects(models_dir)
        return func.HttpResponse(json.dumps(projects, ensure_ascii=False),
                                 status_code=200, mimetype="application/json")
    except Exception as e:
        logger.error(f"ListProjects error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@projects_bp.route(route="CreateProject", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def create_project_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/CreateProject
    Body: {display_name, sector, client_context?, custom_hierarchy?, hierarchy_filename?}
    """
    try:
        body = req.get_json()
        models_dir = get_models_dir()
        project = create_project(body, models_dir)

        return func.HttpResponse(json.dumps(project, ensure_ascii=False),
                                 status_code=201, mimetype="application/json")
    except Exception as e:
        logger.error(f"CreateProject error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@projects_bp.route(route="UpdateProject", methods=["PUT"], auth_level=func.AuthLevel.ANONYMOUS)
def update_project_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """PUT /api/UpdateProject
    Body: {project_id, display_name?, client_context?, custom_hierarchy?, ...}
    """
    try:
        body = req.get_json()
        project_id = body.get("project_id", "").strip()
        if not project_id:
            return func.HttpResponse(json.dumps({"error": "project_id is required"}),
                                     status_code=400, mimetype="application/json")
        models_dir = get_models_dir()
        project = update_project(project_id, body, models_dir)
        return func.HttpResponse(json.dumps(project, ensure_ascii=False),
                                 status_code=200, mimetype="application/json")
    except Exception as e:
        logger.error(f"UpdateProject error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@projects_bp.route(route="DeleteProject", methods=["DELETE"], auth_level=func.AuthLevel.ANONYMOUS)
def delete_project_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """DELETE /api/DeleteProject?projectId=xxx"""
    try:
        project_id = req.params.get("projectId", "").strip()
        if not project_id:
            return func.HttpResponse(json.dumps({"error": "projectId is required"}),
                                     status_code=400, mimetype="application/json")
        models_dir = get_models_dir()
        success = delete_project(project_id, models_dir)
        if not success:
            return func.HttpResponse(json.dumps({"error": "Project not found"}),
                                     status_code=404, mimetype="application/json")
        return func.HttpResponse(json.dumps({"success": True}),
                                 status_code=200, mimetype="application/json")
    except Exception as e:
        logger.error(f"DeleteProject error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@projects_bp.route(route="GetProjectHierarchy", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def get_project_hierarchy_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetProjectHierarchy?projectId=xxx"""
    try:
        project_id = req.params.get("projectId", "").strip()
        if not project_id:
            return func.HttpResponse(json.dumps({"error": "projectId is required"}),
                                     status_code=400, mimetype="application/json")
        models_dir = get_models_dir()
        hierarchy, source = resolve_hierarchy(project_id, models_dir)
        return func.HttpResponse(json.dumps({
            "project_id": project_id,
            "hierarchy": hierarchy,
            "source": source,
            "has_hierarchy": hierarchy is not None
        }, ensure_ascii=False), status_code=200, mimetype="application/json")
    except Exception as e:
        logger.error(f"GetProjectHierarchy error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


