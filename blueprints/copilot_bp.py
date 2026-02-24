"""Blueprint for Copilot / Direct Line and Memory endpoints."""
import json
import logging
import os

import requests
import azure.functions as func
from src.utils import get_models_dir, safe_json_dumps

logger = logging.getLogger(__name__)
copilot_bp = func.Blueprint()


@copilot_bp.route(route="get-token", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def GetDirectLineToken(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/get-token
    Generate a temporary Direct Line token for the frontend to use.

    Exchanges the Direct Line secret (stored in DIRECT_LINE_SECRET env var) for a
    temporary conversation token. The secret never leaves the backend; tokens expire
    after 30 minutes.

    Returns: {token, conversationId, ...} from the Direct Line API.
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )

    logger.info("GetDirectLineToken HTTP trigger processed a request.")

    direct_line_secret = os.getenv("DIRECT_LINE_SECRET")
    if not direct_line_secret:
        logger.error("DIRECT_LINE_SECRET environment variable not configured")
        return func.HttpResponse(
            body=safe_json_dumps({"error": "Direct Line not configured"}),
            status_code=500,
            mimetype="application/json",
        )

    try:
        response = requests.post(
            "https://directline.botframework.com/v3/directline/conversations",
            headers={
                "Authorization": f"Bearer {direct_line_secret}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )

        if response.status_code in (200, 201):
            conversation_data = response.json()
            logger.info(f"Direct Line conversation created: {conversation_data.get('conversationId')}")
            return func.HttpResponse(
                body=safe_json_dumps(conversation_data),
                status_code=200,
                mimetype="application/json",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                },
            )
        else:
            logger.error(f"Direct Line API error: {response.status_code} - {response.text}")
            return func.HttpResponse(
                safe_json_dumps({"error": "Failed to create conversation"}),
                status_code=response.status_code,
                mimetype="application/json",
            )

    except requests.exceptions.RequestException as e:
        logger.error(f"Request to Direct Line API failed: {e}")
        return func.HttpResponse(
            safe_json_dumps({"error": "Network error contacting Direct Line"}),
            status_code=500,
            mimetype="application/json",
        )
    except Exception as e:
        logger.error(f"Unexpected error in GetDirectLineToken: {e}")
        return func.HttpResponse(
            safe_json_dumps({"error": "Internal server error"}),
            status_code=500,
            mimetype="application/json",
        )


@copilot_bp.route(route="SearchMemory", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def SearchMemory(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/SearchMemory?query=xxx
    Search the memory engine (RAG rules) by query string.
    Returns: list of matching memory rules/records.
    """
    logger.info("SearchMemory HTTP trigger processed a request.")

    if req.method == "OPTIONS":
        return func.HttpResponse(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )

    query = req.params.get("query", "")

    try:
        from src.memory_engine import MemoryEngine
        engine = MemoryEngine()
        results = engine.search(query)

        return func.HttpResponse(
            json.dumps(results),
            mimetype="application/json",
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        return func.HttpResponse(str(e), status_code=500)


@copilot_bp.route(route="DeleteMemoryRule", methods=["DELETE", "GET", "OPTIONS"],
                   auth_level=func.AuthLevel.ANONYMOUS)
def DeleteMemoryRule(req: func.HttpRequest) -> func.HttpResponse:
    """DELETE /api/DeleteMemoryRule?id=xxx
    Delete a memory rule by ID.

    The rule ID can be provided as a query param (?id=xxx) or in the JSON body ({id: xxx}).
    Returns: {success: true} or 404 if not found.
    """
    logger.info("DeleteMemoryRule HTTP trigger processed a request.")

    if req.method == "OPTIONS":
        return func.HttpResponse(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "DELETE, GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )

    rule_id = req.params.get("id")
    if not rule_id:
        try:
            body = req.get_json()
            rule_id = body.get("id")
        except Exception:
            pass

    if not rule_id:
        return func.HttpResponse("Missing rule ID", status_code=400)

    try:
        from src.memory_engine import MemoryEngine
        engine = MemoryEngine()
        success = engine.delete_rule(rule_id)

        if success:
            return func.HttpResponse(
                json.dumps({"success": True}),
                mimetype="application/json",
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "DELETE, GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                },
            )
        else:
            return func.HttpResponse("Rule not found", status_code=404)
    except Exception as e:
        logger.error(f"Error deleting memory rule: {e}")
        return func.HttpResponse(str(e), status_code=500)
