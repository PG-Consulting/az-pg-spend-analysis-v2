"""Tests for project hierarchy resolution — parsing b64 Excel into custom_hierarchy."""

import io
import os
import sys
import json
import types
import base64
import pytest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock azure.functions before importing blueprints (same pattern as
# test_classification_bp.py / test_review_bp.py)
# ---------------------------------------------------------------------------
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


class _MockAuthLevel:
    ANONYMOUS = "ANONYMOUS"


class _MockBlueprint:
    def route(self, *a, **kw):
        def decorator(fn):
            return fn

        return decorator


_mock_func.HttpResponse = _MockHttpResponse
_mock_func.HttpRequest = MagicMock
_mock_func.AuthLevel = _MockAuthLevel
_mock_func.Blueprint = _MockBlueprint
_mock_azure.functions = _mock_func
sys.modules["azure"] = _mock_azure
sys.modules["azure.functions"] = _mock_func

from src.exceptions import ValidationError
from src.project_manager import parse_hierarchy_from_b64, resolve_hierarchy_from_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hierarchy_excel_b64():
    """Create a minimal Excel file with N1-N4 hierarchy and return as base64."""
    import pandas as pd

    data = [
        {"N1": "Operação", "N2": "Materiais", "N3": "OEM", "N4": "Peças ABB"},
        {"N1": "Operação", "N2": "Materiais", "N3": "OEM", "N4": "Peças Siemens"},
        {"N1": "Projetos", "N2": "Civil", "N3": "Fundações", "N4": "Estacas"},
    ]
    df = pd.DataFrame(data)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _make_excel_wrong_headers_b64():
    """Create a REAL Excel file whose headers are NOT N1-N4 (parser must fail).

    Reproduz o caso de produção: planilha de hierarquia válida como Excel,
    mas com cabeçalhos não reconhecidos pelo parser.
    """
    import pandas as pd

    data = [
        {
            "Nivel 1": "Operação",
            "Nivel 2": "Materiais",
            "Nivel 3": "OEM",
            "Nivel 4": "Peças ABB",
        },
        {
            "Nivel 1": "Projetos",
            "Nivel 2": "Civil",
            "Nivel 3": "Fundações",
            "Nivel 4": "Estacas",
        },
    ]
    df = pd.DataFrame(data)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ---------------------------------------------------------------------------
# parse_hierarchy_from_b64
# ---------------------------------------------------------------------------


class TestParseHierarchyFromB64:
    def test_parses_valid_excel(self):
        b64 = _make_hierarchy_excel_b64()
        result = parse_hierarchy_from_b64(b64)
        assert result is not None
        assert len(result) == 3
        assert result[0]["N1"] == "Operação"
        assert result[2]["N4"] == "Estacas"

    def test_returns_none_for_empty_string(self):
        assert parse_hierarchy_from_b64("") is None

    def test_returns_none_for_none(self):
        assert parse_hierarchy_from_b64(None) is None

    def test_returns_none_for_invalid_data(self):
        bad_b64 = base64.b64encode(b"not an excel file").decode()
        assert parse_hierarchy_from_b64(bad_b64) is None


# ---------------------------------------------------------------------------
# resolve_hierarchy_from_body
# ---------------------------------------------------------------------------


class TestResolveHierarchyFromBody:
    def test_parses_hierarchy_file_b64(self):
        """Frontend sends hierarchy_file_base64 → should be parsed into custom_hierarchy."""
        b64 = _make_hierarchy_excel_b64()
        body = {
            "display_name": "Test Project",
            "sector": "test",
            "hierarchy_file_base64": b64,
            "hierarchy_source": "own",
        }
        resolve_hierarchy_from_body(body)

        assert body["custom_hierarchy"] is not None
        assert len(body["custom_hierarchy"]) == 3
        assert body["hierarchy_source"] == "own"
        assert "hierarchy_file_base64" not in body  # should be popped

    def test_existing_custom_hierarchy_takes_precedence(self):
        """If custom_hierarchy is already a list, don't touch it."""
        existing = [{"N1": "A", "N2": "B", "N3": "C", "N4": "D"}]
        body = {
            "custom_hierarchy": existing,
            "hierarchy_file_base64": "should_be_ignored",
        }
        resolve_hierarchy_from_body(body)
        assert body["custom_hierarchy"] == existing

    def test_no_hierarchy_sets_padrao(self):
        """No hierarchy provided → hierarchy_source defaults to 'padrao'."""
        body = {"display_name": "Test", "sector": "test"}
        resolve_hierarchy_from_body(body)
        assert body["hierarchy_source"] == "padrao"

    def test_no_hierarchy_preserves_explicit_source(self):
        """If caller explicitly sets hierarchy_source, preserve it."""
        body = {"display_name": "Test", "sector": "test", "hierarchy_source": "own"}
        resolve_hierarchy_from_body(body)
        # setdefault won't overwrite existing "own"
        assert body["hierarchy_source"] == "own"

    def test_failed_b64_parse_raises_validation_error(self):
        """Invalid b64 file → ValidationError (não pode falhar silenciosamente).

        Comportamento antigo (bug de produção): logava warning e seguia,
        persistindo o projeto sem hierarquia.
        """
        bad_b64 = base64.b64encode(b"garbage").decode()
        body = {
            "display_name": "Test",
            "sector": "test",
            "hierarchy_file_base64": bad_b64,
        }
        with pytest.raises(ValidationError):
            resolve_hierarchy_from_body(body)

    def test_b64_removed_from_body(self):
        """hierarchy_file_base64 should be popped (not stored in project config)."""
        b64 = _make_hierarchy_excel_b64()
        body = {"hierarchy_file_base64": b64}
        resolve_hierarchy_from_body(body)
        assert "hierarchy_file_base64" not in body


# ---------------------------------------------------------------------------
# Regressão: arquivo de hierarquia inválido NÃO pode ser engolido em silêncio
# (bug de produção — projeto "teste" persistido com own + custom_hierarchy=None,
#  job rodou sem taxonomia e queimou créditos LLM com 100% fallback)
# ---------------------------------------------------------------------------


class TestInvalidHierarchyFileRejected:
    def test_unrecognized_headers_raise_validation_error(self):
        """Excel real sem colunas N1-N4 + hierarchy_source='own' → ValidationError.

        Antes do fix: passava silenciosamente deixando own + custom_hierarchy=None.
        """
        body = {
            "display_name": "teste",
            "sector": "naval",
            "hierarchy_file_base64": _make_excel_wrong_headers_b64(),
            "hierarchy_source": "own",
        }
        with pytest.raises(ValidationError) as exc_info:
            resolve_hierarchy_from_body(body)

        # Mensagem deve orientar o consultor sobre o que o parser espera
        msg = str(exc_info.value)
        assert "N1" in msg and "N4" in msg
        # Estado inconsistente não pode vazar para o config
        assert not body.get("custom_hierarchy")

    def test_valid_file_still_parses_normally(self):
        """Sanity: arquivo válido continua sendo parseado sem exceção."""
        body = {
            "display_name": "teste",
            "sector": "naval",
            "hierarchy_file_base64": _make_hierarchy_excel_b64(),
            "hierarchy_source": "own",
        }
        resolve_hierarchy_from_body(body)
        assert len(body["custom_hierarchy"]) == 3
        assert body["hierarchy_source"] == "own"


class TestCreateProjectEndpointRejectsInvalidHierarchy:
    """Endpoint-level: CreateProject com hierarquia inválida → 400 e nenhum
    diretório de projeto criado."""

    def test_returns_400_and_no_project_dir_created(self, tmp_path, monkeypatch):
        models_dir = tmp_path / "models"
        (models_dir / "projects").mkdir(parents=True)
        monkeypatch.setattr(
            "blueprints.projects_bp.get_models_dir", lambda: str(models_dir)
        )

        from blueprints.projects_bp import create_project_endpoint

        req = MagicMock()
        req.method = "POST"
        req.get_json.return_value = {
            "display_name": "teste",
            "sector": "naval",
            "hierarchy_file_base64": _make_excel_wrong_headers_b64(),
            "hierarchy_filename": "Versao Revisada Taxonomia.xlsx",
            "hierarchy_source": "own",
        }

        response = create_project_endpoint(req)

        assert response.status_code == 400
        payload = json.loads(response.get_body())
        assert "hierarquia" in payload["error"].lower()
        # Projeto NÃO pode ter sido persistido
        assert os.listdir(models_dir / "projects") == []


# ---------------------------------------------------------------------------
# Regressão: UpdateProject sem campos de hierarquia NÃO pode rebaixar
# hierarchy_source own→padrao. O EditProjectModal envia só display_name/
# client_context/use_sector_kb; o setdefault("padrao") de
# resolve_hierarchy_from_body corrompia projetos saudáveis em qualquer edição
# e desarmava o guard de submit do projeto quebrado (own + None).
# ---------------------------------------------------------------------------


class TestUpdateProjectKeepsHierarchySource:
    _OWN_HIERARCHY = [
        {"N1": "Operação", "N2": "Materiais", "N3": "OEM", "N4": "Peças ABB"},
        {"N1": "Projetos", "N2": "Civil", "N3": "Fundações", "N4": "Estacas"},
    ]

    def _setup(self, tmp_path, monkeypatch):
        models_dir = tmp_path / "models"
        (models_dir / "projects").mkdir(parents=True)
        monkeypatch.setattr(
            "blueprints.projects_bp.get_models_dir", lambda: str(models_dir)
        )
        return models_dir

    def _write_project_config(self, models_dir, project_id, config):
        proj_dir = models_dir / "projects" / project_id
        proj_dir.mkdir(parents=True)
        (proj_dir / "project_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

    def _read_config(self, models_dir, project_id):
        path = models_dir / "projects" / project_id / "project_config.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _edit_modal_body(self, project_id):
        """Body real do EditProjectModal — sem nenhum campo de hierarquia."""
        return {
            "project_id": project_id,
            "display_name": "ACME Editado",
            "client_context": "novo contexto do cliente",
            "use_sector_kb": False,
        }

    def test_update_without_hierarchy_fields_keeps_own_and_list(
        self, tmp_path, monkeypatch
    ):
        """Projeto saudável (own + lista): edição não-relacionada preserva tudo."""
        models_dir = self._setup(tmp_path, monkeypatch)
        self._write_project_config(
            models_dir,
            "naval-acme",
            {
                "project_id": "naval-acme",
                "display_name": "ACME",
                "sector": "naval",
                "client_context": "",
                "custom_hierarchy": self._OWN_HIERARCHY,
                "hierarchy_source": "own",
                "created_at": "2026-01-01T00:00:00+00:00",
                "use_sector_kb": True,
            },
        )

        from blueprints.projects_bp import update_project_endpoint

        req = MagicMock()
        req.method = "PUT"
        req.get_json.return_value = self._edit_modal_body("naval-acme")

        response = update_project_endpoint(req)

        assert response.status_code == 200
        config = self._read_config(models_dir, "naval-acme")
        assert config["hierarchy_source"] == "own"
        assert config["custom_hierarchy"] == self._OWN_HIERARCHY
        # Os campos editados foram aplicados normalmente
        assert config["display_name"] == "ACME Editado"
        assert config["use_sector_kb"] is False

    def test_update_without_hierarchy_fields_keeps_broken_own_state(
        self, tmp_path, monkeypatch
    ):
        """Projeto quebrado (own + None): edição mantém 'own' — o guard do
        SubmitTaxonomyJob continua armado em vez de ser desarmado em silêncio."""
        models_dir = self._setup(tmp_path, monkeypatch)
        self._write_project_config(
            models_dir,
            "teste",
            {
                "project_id": "teste",
                "display_name": "teste",
                "sector": "naval",
                "client_context": "",
                "custom_hierarchy": None,
                "hierarchy_source": "own",
                "created_at": "2026-01-01T00:00:00+00:00",
                "use_sector_kb": True,
            },
        )

        from blueprints.projects_bp import update_project_endpoint

        req = MagicMock()
        req.method = "PUT"
        req.get_json.return_value = self._edit_modal_body("teste")

        response = update_project_endpoint(req)

        assert response.status_code == 200
        config = self._read_config(models_dir, "teste")
        assert config["hierarchy_source"] == "own"

    def test_update_with_valid_hierarchy_file_still_replaces(
        self, tmp_path, monkeypatch
    ):
        """Preservado: update COM hierarchy_file_base64 válido troca a
        hierarquia e marca source='own'."""
        models_dir = self._setup(tmp_path, monkeypatch)
        self._write_project_config(
            models_dir,
            "naval-acme",
            {
                "project_id": "naval-acme",
                "display_name": "ACME",
                "sector": "naval",
                "client_context": "",
                "custom_hierarchy": None,
                "hierarchy_source": "padrao",
                "created_at": "2026-01-01T00:00:00+00:00",
                "use_sector_kb": True,
            },
        )

        from blueprints.projects_bp import update_project_endpoint

        req = MagicMock()
        req.method = "PUT"
        req.get_json.return_value = {
            "project_id": "naval-acme",
            "hierarchy_file_base64": _make_hierarchy_excel_b64(),
            "hierarchy_filename": "hierarquia.xlsx",
        }

        response = update_project_endpoint(req)

        assert response.status_code == 200
        config = self._read_config(models_dir, "naval-acme")
        assert config["hierarchy_source"] == "own"
        assert len(config["custom_hierarchy"]) == 3

    def test_create_without_hierarchy_still_persists_padrao(
        self, tmp_path, monkeypatch
    ):
        """Preservado: CreateProject sem hierarquia → hierarchy_source='padrao'."""
        models_dir = self._setup(tmp_path, monkeypatch)

        from blueprints.projects_bp import create_project_endpoint

        req = MagicMock()
        req.method = "POST"
        req.get_json.return_value = {
            "display_name": "Naval Sem Hierarquia",
            "sector": "naval",
        }

        response = create_project_endpoint(req)

        assert response.status_code == 201
        config = self._read_config(models_dir, "naval-sem-hierarquia")
        assert config["hierarchy_source"] == "padrao"
        assert config["custom_hierarchy"] is None
