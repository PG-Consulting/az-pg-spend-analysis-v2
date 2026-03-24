"""Health check endpoint — quick liveness/readiness probe."""

import os
import time
import logging

import azure.functions as func

from src.api_helpers import json_response, handle_errors
from src.utils import get_models_dir

logger = logging.getLogger(__name__)
health_bp = func.Blueprint()

# Cache for Grok probe (avoid calling API on every health check)
_grok_probe_cache = {"result": None, "timestamp": 0}
_PROBE_CACHE_TTL = 300  # 5 minutes


def _probe_grok_api() -> dict:
    """Test Grok API connectivity with a minimal request. Cached for 5 minutes."""
    now = time.time()
    if (
        _grok_probe_cache["result"]
        and (now - _grok_probe_cache["timestamp"]) < _PROBE_CACHE_TTL
    ):
        return _grok_probe_cache["result"]

    import requests

    api_key = os.environ.get("GROK_API_KEY", "")
    endpoint = os.environ.get("GROK_API_ENDPOINT", "https://api.x.ai/v1")
    model = os.environ.get("GROK_MODEL_NAME", "grok-4-1-fast-reasoning")

    if not api_key:
        result = {"reachable": False, "latency_ms": 0}
        _grok_probe_cache["result"] = result
        _grok_probe_cache["timestamp"] = now
        return result

    try:
        start = time.time()
        response = requests.post(
            f"{endpoint.rstrip('/')}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "temperature": 0,
            },
            timeout=10,
        )
        latency = round((time.time() - start) * 1000)
        reachable = response.status_code == 200
        result = {"reachable": reachable, "latency_ms": latency}
    except Exception:
        result = {"reachable": False, "latency_ms": 0}

    _grok_probe_cache["result"] = result
    _grok_probe_cache["timestamp"] = now
    return result


@health_bp.route(route="health", methods=["GET"])
@handle_errors("HealthCheck")
def HealthCheck(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/health — returns service status.

    Public: minimal status only.
    Authenticated admin (or SKIP_AUTH dev): full diagnostic checks.
    """
    from src.auth import _is_skip_auth_allowed, _extract_and_validate
    from src.exceptions import AuthenticationError, ForbiddenError

    # Determine if caller is authenticated admin
    show_details = False
    if _is_skip_auth_allowed():
        show_details = True
    else:
        try:
            user = _extract_and_validate(req)
            show_details = user.get("role") == "admin"
        except (AuthenticationError, ForbiddenError):
            pass  # Not authenticated or not authorized — show public response

    if not show_details:
        return json_response({"status": "healthy", "version": "3.0"})

    # Full diagnostics for admin
    models_dir = get_models_dir()
    grok_probe = _probe_grok_api()

    checks = {
        "filesystem": os.path.isdir(models_dir),
        "grok_api_configured": bool(os.environ.get("GROK_API_KEY")),
        "grok_api_reachable": grok_probe["reachable"],
        "grok_api_latency_ms": grok_probe["latency_ms"],
        "models_dir_configured": bool(models_dir),
    }

    if not checks["filesystem"] or not checks["grok_api_reachable"]:
        status = "degraded"
    else:
        status = "healthy"

    return json_response({"status": status, "version": "3.0", "checks": checks})
