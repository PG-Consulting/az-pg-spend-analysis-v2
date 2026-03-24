"""Standardized API response helpers and error handling decorator."""

import json
import logging
import os
import functools

import azure.functions as func
import filelock

from src.utils import safe_json_dumps
from src.exceptions import SpendAnalysisError

logger = logging.getLogger(__name__)

# --- CORS helpers ---

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]


def _resolve_origin(request) -> str:
    """Return the request Origin if it is in ALLOWED_ORIGINS, else the first allowed origin."""
    if request is not None:
        origin = None
        try:
            origin = request.headers.get("Origin")
        except Exception:
            pass
        if origin and origin in ALLOWED_ORIGINS:
            return origin
    return ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "http://localhost:3000"


def _cors_headers(request=None) -> dict:
    """Build CORS + security response headers with dynamic origin."""
    return {
        "Access-Control-Allow-Origin": _resolve_origin(request),
        "Access-Control-Allow-Credentials": "true",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }


def json_response(
    data, status_code: int = 200, headers: dict = None, request=None
) -> func.HttpResponse:
    """Create a JSON HttpResponse using safe_json_dumps."""
    resp_headers = _cors_headers(request)
    if headers:
        resp_headers.update(headers)
    return func.HttpResponse(
        body=safe_json_dumps(data),
        status_code=status_code,
        mimetype="application/json",
        headers=resp_headers,
    )


def error_response(
    message: str, status_code: int = 500, request=None
) -> func.HttpResponse:
    """Create a standardized error response: {"error": "message"}."""
    return func.HttpResponse(
        body=json.dumps({"error": message}, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
        headers=_cors_headers(request),
    )


def options_response(req_or_methods=None, methods: str = None) -> func.HttpResponse:
    """Create a CORS preflight response.

    Backwards-compatible:
        options_response("GET, POST, OPTIONS")           # old style
        options_response(req, "GET, POST, OPTIONS")      # new style with request
    """
    if req_or_methods is None or isinstance(req_or_methods, str):
        # Old-style call: options_response() or options_response("GET, OPTIONS")
        request = None
        actual_methods = req_or_methods or "GET, POST, OPTIONS"
    else:
        # New-style call: options_response(req, "GET, OPTIONS")
        request = req_or_methods
        actual_methods = methods or "GET, POST, OPTIONS"

    cors = _cors_headers(request)
    cors["Access-Control-Allow-Methods"] = actual_methods
    cors["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return func.HttpResponse(status_code=200, headers=cors)


def handle_errors(func_or_name=None):
    """Decorator that catches exceptions and returns standardized error responses.

    Usage:
        @handle_errors
        def my_endpoint(req): ...

        @handle_errors("MyEndpoint")
        def my_endpoint(req): ...
    """

    def decorator(fn):
        endpoint_name = func_or_name if isinstance(func_or_name, str) else fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Extract request object for CORS headers
            req = args[0] if args and hasattr(args[0], "headers") else None
            try:
                return fn(*args, **kwargs)
            except filelock.Timeout:
                logger.warning(f"{endpoint_name}: file lock timeout — recurso ocupado")
                return func.HttpResponse(
                    body=json.dumps(
                        {"error": "Recurso temporariamente ocupado. Tente novamente."},
                        ensure_ascii=False,
                    ),
                    status_code=503,
                    mimetype="application/json",
                    headers={
                        **_cors_headers(req),
                        "Retry-After": "2",
                    },
                )
            except SpendAnalysisError as e:
                logger.warning(f"{endpoint_name}: {e}")
                return error_response(str(e), e.status_code, request=req)
            except ValueError as e:
                logger.warning(f"{endpoint_name} validation error: {e}")
                return error_response(str(e), 400, request=req)
            except Exception as e:
                logger.error(f"{endpoint_name} error: {e}", exc_info=True)
                return error_response(str(e), 500, request=req)

        return wrapper

    if callable(func_or_name):
        return decorator(func_or_name)
    return decorator


# --- Rate limiting ---

import threading  # noqa: E402
import time as _time  # noqa: E402
from collections import defaultdict  # noqa: E402

_rate_limit_buckets: dict = defaultdict(list)
_rate_limit_lock = threading.Lock()


def _get_client_ip(request) -> str:
    """Extract client IP from request (handles Azure proxy headers)."""
    if request is None:
        return "unknown"
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.headers.get("X-Client-IP", "unknown")


def rate_limit(requests: int = 100, window: int = 60):
    """Decorator: per-IP sliding window rate limiter.

    Returns 429 with Retry-After header when limit is exceeded.
    Bypasses OPTIONS preflight requests.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            req = args[0] if args and hasattr(args[0], "headers") else None

            # Bypass OPTIONS
            if req and hasattr(req, "method") and req.method == "OPTIONS":
                return fn(*args, **kwargs)

            client_ip = _get_client_ip(req)
            now = _time.time()

            with _rate_limit_lock:
                bucket = _rate_limit_buckets[client_ip]
                bucket[:] = [ts for ts in bucket if now - ts < window]

                if len(bucket) >= requests:
                    reset_time = bucket[0] + window
                    return func.HttpResponse(
                        body=json.dumps(
                            {"error": "Rate limit exceeded. Try again later."},
                            ensure_ascii=False,
                        ),
                        status_code=429,
                        mimetype="application/json",
                        headers={
                            **_cors_headers(req),
                            "Retry-After": str(int(reset_time - now) + 1),
                        },
                    )

                bucket.append(now)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
