"""Blueprint for Copilot / Direct Line and Memory endpoints."""
import logging
import os

import requests
import azure.functions as func
from src.api_helpers import json_response, error_response, options_response, handle_errors
from src.exceptions import ValidationError, ExternalServiceError, NotFoundError

logger = logging.getLogger(__name__)
copilot_bp = func.Blueprint()


@copilot_bp.route(route="get-token", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("GetDirectLineToken")
def GetDirectLineToken(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/get-token
    Generate a temporary Direct Line token for the frontend to use.

    Exchanges the Direct Line secret (stored in DIRECT_LINE_SECRET env var) for a
    temporary conversation token. The secret never leaves the backend; tokens expire
    after 30 minutes.

    Returns: {token, conversationId, ...} from the Direct Line API.
    """
    if req.method == "OPTIONS":
        return options_response("GET, OPTIONS")

    logger.info("GetDirectLineToken HTTP trigger processed a request.")

    direct_line_secret = os.getenv("DIRECT_LINE_SECRET")
    if not direct_line_secret:
        logger.error("DIRECT_LINE_SECRET environment variable not configured")
        raise ExternalServiceError("Direct Line", "not configured")

    try:
        response = requests.post(
            "https://directline.botframework.com/v3/directline/conversations",
            headers={
                "Authorization": f"Bearer {direct_line_secret}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Request to Direct Line API failed: {e}")
        raise ExternalServiceError("Direct Line", str(e))

    if response.status_code in (200, 201):
        conversation_data = response.json()
        logger.info(f"Direct Line conversation created: {conversation_data.get('conversationId')}")
        return json_response(conversation_data)
    else:
        logger.error(f"Direct Line API error: {response.status_code} - {response.text}")
        raise ExternalServiceError("Direct Line", "Failed to create conversation")


@copilot_bp.route(route="SearchMemory", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("SearchMemory")
def SearchMemory(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/SearchMemory?query=xxx
    Search the memory engine (RAG rules) by query string.
    Returns: list of matching memory rules/records.
    """
    logger.info("SearchMemory HTTP trigger processed a request.")

    if req.method == "OPTIONS":
        return options_response("GET, OPTIONS")

    query = req.params.get("query", "")

    from src.memory_engine import MemoryEngine
    engine = MemoryEngine()
    results = engine.search(query)

    return json_response(results)


@copilot_bp.route(route="DeleteMemoryRule", methods=["DELETE", "OPTIONS"],
                   auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("DeleteMemoryRule")
def DeleteMemoryRule(req: func.HttpRequest) -> func.HttpResponse:
    """DELETE /api/DeleteMemoryRule?id=xxx
    Delete a memory rule by ID.

    The rule ID can be provided as a query param (?id=xxx) or in the JSON body ({id: xxx}).
    Returns: {success: true} or 404 if not found.
    """
    logger.info("DeleteMemoryRule HTTP trigger processed a request.")

    if req.method == "OPTIONS":
        return options_response("DELETE, OPTIONS")

    rule_id = req.params.get("id")
    if not rule_id:
        try:
            body = req.get_json()
            rule_id = body.get("id")
        except Exception:
            pass

    if not rule_id:
        raise ValidationError("Missing rule ID")

    from src.memory_engine import MemoryEngine
    engine = MemoryEngine()
    success = engine.delete_rule(rule_id)

    if success:
        return json_response({"success": True})
    else:
        raise NotFoundError("Rule", rule_id)
