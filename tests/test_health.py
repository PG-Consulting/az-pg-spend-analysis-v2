"""Tests for blueprints/health_bp.py — HealthCheck endpoint."""

import json
import os
import sys
import types
from unittest.mock import patch


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

    def __init__(self, method="GET", url="", params=None, body=None, headers=None):
        self.method = method
        self.url = url
        self.params = params or {}
        self.headers = headers or {}
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
    def test_public_returns_minimal_info(self):
        """Health endpoint without auth returns only status and version."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("SKIP_AUTH", "WEBSITE_SITE_NAME")
        }
        with patch.dict(os.environ, env, clear=True):
            resp = HealthCheck(_MockHttpRequest())

        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        assert body == {"status": "healthy", "version": "3.0"}
        assert "checks" not in body

    @patch(
        "blueprints.health_bp._probe_grok_api",
        return_value={"reachable": True, "latency_ms": 50},
    )
    def test_returns_200_with_expected_fields(self, mock_probe, tmp_path):
        """Health endpoint returns 200 with status, version, and checks."""
        models_dir = str(tmp_path / "models")
        os.makedirs(models_dir)

        with patch("blueprints.health_bp.get_models_dir", return_value=models_dir):
            with patch.dict(
                os.environ,
                {"GROK_API_KEY": "test-key-123", "SKIP_AUTH": "true"},
                clear=False,
            ):
                env = {k: v for k, v in os.environ.items() if k != "WEBSITE_SITE_NAME"}
                env["GROK_API_KEY"] = "test-key-123"
                env["SKIP_AUTH"] = "true"
                with patch.dict(os.environ, env, clear=True):
                    resp = HealthCheck(_MockHttpRequest())

        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        assert body["status"] == "healthy"
        assert body["version"] == "3.0"
        assert body["checks"]["filesystem"] is True
        assert body["checks"]["grok_api_configured"] is True
        assert body["checks"]["grok_api_reachable"] is True
        assert body["checks"]["grok_api_latency_ms"] == 50
        assert body["checks"]["models_dir_configured"] is True

    @patch(
        "blueprints.health_bp._probe_grok_api",
        return_value={"reachable": False, "latency_ms": 0},
    )
    def test_degraded_when_models_dir_missing(self, mock_probe):
        """Health reports degraded when models_dir doesn't exist."""
        fake_dir = "/nonexistent/path/models"
        with patch("blueprints.health_bp.get_models_dir", return_value=fake_dir):
            # Remove GROK_API_KEY and WEBSITE_SITE_NAME, add SKIP_AUTH
            env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("GROK_API_KEY", "WEBSITE_SITE_NAME")
            }
            env["SKIP_AUTH"] = "true"
            with patch.dict(os.environ, env, clear=True):
                resp = HealthCheck(_MockHttpRequest())

        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        assert body["status"] == "degraded"
        assert body["checks"]["filesystem"] is False
        assert body["checks"]["grok_api_configured"] is False

    @patch(
        "blueprints.health_bp._probe_grok_api",
        return_value={"reachable": True, "latency_ms": 50},
    )
    def test_cors_headers(self, mock_probe, tmp_path):
        """Health endpoint includes CORS headers."""
        models_dir = str(tmp_path / "models")
        os.makedirs(models_dir)

        with patch("blueprints.health_bp.get_models_dir", return_value=models_dir):
            with patch.dict(os.environ, {"SKIP_AUTH": "true"}, clear=False):
                env = {k: v for k, v in os.environ.items() if k != "WEBSITE_SITE_NAME"}
                env["SKIP_AUTH"] = "true"
                with patch.dict(os.environ, env, clear=True):
                    resp = HealthCheck(_MockHttpRequest())

        assert "Access-Control-Allow-Origin" in resp.headers


class TestGrokProbe:
    """Health check deve testar conectividade com a API Grok."""

    @patch("src.auth._is_skip_auth_allowed", return_value=True)
    @patch("blueprints.health_bp.os.path.isdir", return_value=True)
    @patch("blueprints.health_bp.os.environ.get")
    @patch(
        "blueprints.health_bp._probe_grok_api",
        return_value={"reachable": True, "latency_ms": 150},
    )
    def test_healthy_when_grok_reachable(
        self, mock_probe, mock_env, mock_isdir, mock_skip
    ):
        """Se Grok responde, status deve ser healthy."""
        mock_env.side_effect = lambda key, *args: (
            "fake-key"
            if key == "GROK_API_KEY"
            else "true"
            if key == "SKIP_AUTH"
            else args[0]
            if args
            else ""
        )
        from blueprints.health_bp import HealthCheck

        req = _MockHttpRequest()
        response = HealthCheck(req)
        body = json.loads(response.get_body())
        assert body["status"] == "healthy"
        assert body["checks"]["grok_api_reachable"] is True

    @patch("src.auth._is_skip_auth_allowed", return_value=True)
    @patch("blueprints.health_bp.os.path.isdir", return_value=True)
    @patch("blueprints.health_bp.os.environ.get")
    @patch(
        "blueprints.health_bp._probe_grok_api",
        return_value={"reachable": False, "latency_ms": 0},
    )
    def test_degraded_when_grok_unreachable(
        self, mock_probe, mock_env, mock_isdir, mock_skip
    ):
        """Se Grok não responde, status deve ser degraded."""
        mock_env.side_effect = lambda key, *args: (
            "fake-key"
            if key == "GROK_API_KEY"
            else "true"
            if key == "SKIP_AUTH"
            else args[0]
            if args
            else ""
        )
        from blueprints.health_bp import HealthCheck

        req = _MockHttpRequest()
        response = HealthCheck(req)
        body = json.loads(response.get_body())
        assert body["status"] == "degraded"
        assert body["checks"]["grok_api_reachable"] is False
