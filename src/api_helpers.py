"""Standardized API response helpers and error handling decorator."""

import json
import logging
import functools

import azure.functions as func
import filelock

from src.utils import safe_json_dumps
from src.exceptions import SpendAnalysisError

logger = logging.getLogger(__name__)


def json_response(
    data, status_code: int = 200, headers: dict = None
) -> func.HttpResponse:
    """Create a JSON HttpResponse using safe_json_dumps."""
    resp_headers = {"Access-Control-Allow-Origin": "*"}
    if headers:
        resp_headers.update(headers)
    return func.HttpResponse(
        body=safe_json_dumps(data),
        status_code=status_code,
        mimetype="application/json",
        headers=resp_headers,
    )


def error_response(message: str, status_code: int = 500) -> func.HttpResponse:
    """Create a standardized error response: {"error": "message"}."""
    return func.HttpResponse(
        body=json.dumps({"error": message}, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


def options_response(methods: str = "GET, POST, OPTIONS") -> func.HttpResponse:
    """Create a CORS preflight response."""
    return func.HttpResponse(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": methods,
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


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
                        "Access-Control-Allow-Origin": "*",
                        "Retry-After": "2",
                    },
                )
            except SpendAnalysisError as e:
                logger.warning(f"{endpoint_name}: {e}")
                return error_response(str(e), e.status_code)
            except ValueError as e:
                logger.warning(f"{endpoint_name} validation error: {e}")
                return error_response(str(e), 400)
            except Exception as e:
                logger.error(f"{endpoint_name} error: {e}", exc_info=True)
                return error_response(str(e), 500)

        return wrapper

    if callable(func_or_name):
        return decorator(func_or_name)
    return decorator
