"""Health check endpoint — quick liveness/readiness probe."""
import os
import logging

import azure.functions as func

from src.api_helpers import json_response, handle_errors
from src.utils import get_models_dir

logger = logging.getLogger(__name__)
health_bp = func.Blueprint()


@health_bp.route(route="health", methods=["GET"])
@handle_errors("HealthCheck")
def HealthCheck(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/health — returns service status and basic checks."""
    models_dir = get_models_dir()

    checks = {
        "filesystem": os.path.isdir(models_dir),
        "grok_api_configured": bool(os.environ.get("GROK_API_KEY")),
        "models_dir": models_dir,
    }

    status = "healthy" if checks["filesystem"] else "degraded"

    return json_response({
        "status": status,
        "version": "3.0",
        "checks": checks,
    })
