"""Tests for blueprints/health_bp.py — HealthCheck endpoint."""
import json
import os
import sys
import types
from unittest.mock import patch

import pytest

# Mock azure.functions before importing
_mock_azure = types.ModuleType("azure")
_mock_func = types.ModuleType("azure.functions")


class _MockHttpResponse:
    """Minimal mock of azure.functions.HttpResponse."""
    def __init__(self, body=None, status_code=200, mimetype=None, headers=None):
        self._body = body.encode("utf-8") if isinstance(body, str) else (body or b"")
        self.status_code = status_code
        self.mimetype = mimetype
        self.headers = headers or {}

    def get_body(self):
        return self._body


class _MockHttpRequest:
    """Minimal mock of azure.functions.HttpRequest."""
    def __init__(self, method="GET", url="", params=None, body=None):
        self.method = method
        self.url = url
        self.params = params or {}
        self._body = body

    def get_json(self):
        return json.loads(self._body) if self._body else {}


class _MockBlueprint:
    """Mock Blueprint that captures route decorators."""
    def __init__(self):
        self._functions = {}

    def route(self, **kwargs):
        def decorator(fn):
            self._functions[kwargs.get("route", fn.__name__)] = fn
            return fn
        return decorator


_mock_func.HttpResponse = _MockHttpResponse
_mock_func.HttpRequest = _MockHttpRequest
_mock_func.Blueprint = _MockBlueprint
_mock_func.AuthLevel = types.SimpleNamespace(ANONYMOUS="anonymous")
_mock_azure.functions = _mock_func
sys.modules["azure"] = _mock_azure
sys.modules["azure.functions"] = _mock_func

# Ensure Blueprint is available if azure.functions was already loaded by another test
if hasattr(sys.modules.get("azure.functions", None), "__dict__"):
    sys.modules["azure.functions"].Blueprint = _MockBlueprint

from blueprints.health_bp import HealthCheck


class TestHealthCheck:
    def test_returns_200_with_expected_fields(self, tmp_path):
        """Health endpoint returns 200 with status, version, and checks."""
        models_dir = str(tmp_path / "models")
        os.makedirs(models_dir)

        with patch("blueprints.health_bp.get_models_dir", return_value=models_dir):
            with patch.dict(os.environ, {"GROK_API_KEY": "test-key-123"}):
                resp = HealthCheck(_MockHttpRequest())

        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        assert body["status"] == "healthy"
        assert body["version"] == "3.0"
        assert body["checks"]["filesystem"] is True
        assert body["checks"]["grok_api_configured"] is True
        assert body["checks"]["models_dir"] == models_dir

    def test_degraded_when_models_dir_missing(self):
        """Health reports degraded when models_dir doesn't exist."""
        fake_dir = "/nonexistent/path/models"
        with patch("blueprints.health_bp.get_models_dir", return_value=fake_dir):
            with patch.dict(os.environ, {}, clear=False):
                # Remove GROK_API_KEY if present
                env = {k: v for k, v in os.environ.items() if k != "GROK_API_KEY"}
                with patch.dict(os.environ, env, clear=True):
                    resp = HealthCheck(_MockHttpRequest())

        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        assert body["status"] == "degraded"
        assert body["checks"]["filesystem"] is False
        assert body["checks"]["grok_api_configured"] is False

    def test_cors_headers(self, tmp_path):
        """Health endpoint includes CORS headers."""
        models_dir = str(tmp_path / "models")
        os.makedirs(models_dir)

        with patch("blueprints.health_bp.get_models_dir", return_value=models_dir):
            resp = HealthCheck(_MockHttpRequest())

        assert resp.headers.get("Access-Control-Allow-Origin") == "*"
