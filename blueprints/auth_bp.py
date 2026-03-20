"""Blueprint for authentication endpoints."""

import logging

import azure.functions as func

from src.api_helpers import json_response, options_response, handle_errors
from src.auth import require_auth

logger = logging.getLogger(__name__)
auth_bp = func.Blueprint()


@auth_bp.route(
    route="GetUserProfile",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetUserProfile")
@require_auth
def get_user_profile(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetUserProfile — returns the authenticated user's profile."""
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    user = req.user
    return json_response(
        {
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
        },
        request=req,
    )
