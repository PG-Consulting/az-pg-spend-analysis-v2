"""Tests for src.project_manager (sector/project CRUD, hierarchy resolution)."""

import os
import json
import pytest
from src.project_manager import (
    _slugify,
    create_sector,
    list_sectors,
    get_sector,
    update_sector,
    delete_sector,
    create_project,
    list_projects,
    get_project,
    update_project,
    delete_project,
    resolve_hierarchy,
)


# ---------------------------------------------------------------------------
# Helper: create a tmp models dir
# ---------------------------------------------------------------------------

@pytest.fixture
def models_dir(tmp_path):
    """Create a temporary models directory with sectors/ and projects/ subdirectories."""
    md = tmp_path / "models"
    (md / "sectors").mkdir(parents=True)
    (md / "projects").mkdir(parents=True)
    return str(md)


# ---------------------------------------------------------------------------
# Tests: _slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_slugify_basic(self):
        """'Naval' becomes 'naval'."""
        assert _slugify("Naval") == "naval"

    def test_slugify_accents(self):
        """'Saude & Bem-Estar' removes accents and special chars."""
        result = _slugify("Saúde & Bem-Estar")
        assert result == "saude-bem-estar"

    def test_slugify_spaces(self):
        """'Naval Offshore' becomes 'naval-offshore'."""
        assert _slugify("Naval Offshore") == "naval-offshore"

    def test_slugify_special(self):
        """'Test@#$Name' strips special characters."""
        result = _slugify("Test@#$Name")
        assert result == "testname"


# ---------------------------------------------------------------------------
# Tests: Sector CRUD
# ---------------------------------------------------------------------------

class TestSectorCRUD:
    def test_create_sector(self, models_dir):
        """Creating a sector returns config with name and display_name."""
        config = create_sector("naval", "Naval", None, models_dir)
        assert config["name"] == "naval"
        assert config["display_name"] == "Naval"
        assert "created_at" in config

        # Verify file exists on disk
        config_path = os.path.join(models_dir, "sectors", "naval", "sector_config.json")
        assert os.path.exists(config_path)

    def test_list_sectors(self, models_dir):
        """Creating 2 sectors and listing returns both."""
        create_sector("naval", "Naval", None, models_dir)
        create_sector("varejo", "Varejo", None, models_dir)

        sectors = list_sectors(models_dir)
        assert len(sectors) == 2
        names = {s["name"] for s in sectors}
        assert names == {"naval", "varejo"}

    def test_get_sector(self, models_dir):
        """Get a previously created sector."""
        create_sector("naval", "Naval", None, models_dir)
        sector = get_sector("naval", models_dir)
        assert sector is not None
        assert sector["name"] == "naval"
        assert sector["display_name"] == "Naval"

    def test_get_sector_not_found(self, models_dir):
        """Getting a nonexistent sector returns None."""
        result = get_sector("nonexistent", models_dir)
        assert result is None

    def test_update_sector(self, models_dir):
        """Updating display_name of an existing sector."""
        create_sector("naval", "Naval", None, models_dir)
        updated = update_sector("naval", {"display_name": "Naval Offshore"}, models_dir)
        assert updated["display_name"] == "Naval Offshore"
        assert updated["name"] == "naval"  # name is immutable

    def test_update_sector_not_found(self, models_dir):
        """Updating a nonexistent sector raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            update_sector("nonexistent", {"display_name": "Test"}, models_dir)


# ---------------------------------------------------------------------------
# Tests: Project CRUD
# ---------------------------------------------------------------------------

class TestProjectCRUD:
    def test_create_project(self, models_dir):
        """Creating a project returns config with project_id, display_name, sector."""
        create_sector("naval", "Naval", None, models_dir)
        config = create_project(
            {"display_name": "Naval Wartsila", "sector": "naval"},
            models_dir,
        )
        assert config["project_id"] == "naval-wartsila"
        assert config["display_name"] == "Naval Wartsila"
        assert config["sector"] == "naval"
        assert "created_at" in config
        assert "updated_at" in config

        # Verify files exist on disk
        project_dir = os.path.join(models_dir, "projects", "naval-wartsila")
        assert os.path.isdir(project_dir)
        assert os.path.exists(os.path.join(project_dir, "project_config.json"))
        assert os.path.exists(os.path.join(project_dir, "knowledge_base.json"))

    def test_create_project_auto_slug(self, models_dir):
        """display_name 'Naval - WARTSILA' generates a slug automatically."""
        create_sector("naval", "Naval", None, models_dir)
        config = create_project(
            {"display_name": "Naval - WÄRTSILÄ", "sector": "naval"},
            models_dir,
        )
        # Accents and special chars should be stripped
        slug = config["project_id"]
        assert slug == "naval-wartsila"
        assert slug.isascii()
        assert " " not in slug

    def test_create_project_empty_name(self, models_dir):
        """Creating a project with empty display_name raises ValueError."""
        with pytest.raises(ValueError, match="display_name"):
            create_project({"display_name": "", "sector": "naval"}, models_dir)

    def test_list_projects(self, models_dir):
        """Creating 2 projects and listing returns both."""
        create_sector("naval", "Naval", None, models_dir)
        create_project({"display_name": "Projeto A", "sector": "naval"}, models_dir)
        create_project({"display_name": "Projeto B", "sector": "naval"}, models_dir)

        projects = list_projects(models_dir)
        assert len(projects) == 2

    def test_get_project(self, models_dir):
        """Get a previously created project by its project_id."""
        create_sector("naval", "Naval", None, models_dir)
        created = create_project(
            {"display_name": "Naval Wartsila", "sector": "naval"},
            models_dir,
        )
        project = get_project(created["project_id"], models_dir)
        assert project is not None
        assert project["display_name"] == "Naval Wartsila"

    def test_update_project(self, models_dir):
        """Updating client_context of an existing project."""
        create_sector("naval", "Naval", None, models_dir)
        created = create_project(
            {"display_name": "Naval Wartsila", "sector": "naval"},
            models_dir,
        )
        updated = update_project(
            created["project_id"],
            {"client_context": "Wartsila marine engines procurement"},
            models_dir,
        )
        assert updated["client_context"] == "Wartsila marine engines procurement"
        # project_id should be immutable
        assert updated["project_id"] == created["project_id"]

    def test_delete_project(self, models_dir):
        """Creating then deleting a project removes the directory."""
        create_sector("naval", "Naval", None, models_dir)
        created = create_project(
            {"display_name": "Naval Wartsila", "sector": "naval"},
            models_dir,
        )
        project_dir = os.path.join(models_dir, "projects", created["project_id"])
        assert os.path.isdir(project_dir)

        result = delete_project(created["project_id"], models_dir)
        assert result is True
        assert not os.path.isdir(project_dir)

    def test_delete_nonexistent(self, models_dir):
        """Deleting a nonexistent project returns False."""
        result = delete_project("nonexistent-project", models_dir)
        assert result is False


# ---------------------------------------------------------------------------
# Tests: use_sector_kb toggle
# ---------------------------------------------------------------------------

class TestUseSectorKB:
    def test_default_use_sector_kb_is_true(self, models_dir):
        """By default, use_sector_kb should be True."""
        create_sector("naval", "Naval", None, models_dir)
        config = create_project(
            {"display_name": "Naval Test", "sector": "naval"},
            models_dir,
        )
        assert config["use_sector_kb"] is True

    def test_create_with_use_sector_kb_false(self, models_dir):
        """Creating a project with use_sector_kb=False persists the value."""
        create_sector("naval", "Naval", None, models_dir)
        config = create_project(
            {"display_name": "Naval Isolated", "sector": "naval", "use_sector_kb": False},
            models_dir,
        )
        assert config["use_sector_kb"] is False

        # Verify persistence
        loaded = get_project(config["project_id"], models_dir)
        assert loaded["use_sector_kb"] is False

    def test_update_use_sector_kb_toggle(self, models_dir):
        """Updating use_sector_kb from True to False works."""
        create_sector("naval", "Naval", None, models_dir)
        config = create_project(
            {"display_name": "Naval Toggle", "sector": "naval"},
            models_dir,
        )
        assert config["use_sector_kb"] is True

        updated = update_project(config["project_id"], {"use_sector_kb": False}, models_dir)
        assert updated["use_sector_kb"] is False

        # Verify persistence
        loaded = get_project(config["project_id"], models_dir)
        assert loaded["use_sector_kb"] is False


# ---------------------------------------------------------------------------
# Tests: resolve_hierarchy
# ---------------------------------------------------------------------------

class TestResolveHierarchy:
    def test_resolve_own_hierarchy(self, models_dir):
        """Project with its own hierarchy returns (hierarchy, 'own')."""
        hierarchy = [
            {"N1": "MRO", "N2": "Fixação", "N3": "Parafusos", "N4": "Parafuso Sextavado"},
        ]
        create_sector("naval", "Naval", None, models_dir)
        created = create_project(
            {
                "display_name": "Naval Wartsila",
                "sector": "naval",
                "custom_hierarchy": hierarchy,
            },
            models_dir,
        )
        result_hierarchy, source = resolve_hierarchy(created["project_id"], models_dir)
        assert source == "own"
        assert result_hierarchy == hierarchy

    def test_resolve_padrao(self, models_dir):
        """Project without hierarchy returns (None, 'padrao')."""
        create_sector("naval", "Naval", None, models_dir)
        created = create_project(
            {"display_name": "Naval Wartsila", "sector": "naval"},
            models_dir,
        )
        result_hierarchy, source = resolve_hierarchy(created["project_id"], models_dir)
        assert source == "padrao"
        assert result_hierarchy is None


# ---------------------------------------------------------------------------
# Tests: delete_sector
# ---------------------------------------------------------------------------

class TestDeleteSector:
    def test_delete_sector_empty(self, models_dir):
        """Deleting a sector with no projects succeeds."""
        create_sector("naval", "Naval", None, models_dir)
        result = delete_sector("naval", models_dir)
        assert result["deleted_sector"] == "naval"
        assert result["deleted_projects"] == []
        # Verify directory removed
        sector_dir = os.path.join(models_dir, "sectors", "naval")
        assert not os.path.isdir(sector_dir)
        # Verify no longer listed
        assert len(list_sectors(models_dir)) == 0

    def test_delete_sector_not_found(self, models_dir):
        """Deleting a nonexistent sector returns empty dict."""
        result = delete_sector("nonexistent", models_dir)
        assert result == {}

    def test_delete_sector_with_projects_no_force(self, models_dir):
        """Deleting a sector with projects and force=False raises ValueError."""
        create_sector("naval", "Naval", None, models_dir)
        create_project({"display_name": "Projeto A", "sector": "naval"}, models_dir)
        create_project({"display_name": "Projeto B", "sector": "naval"}, models_dir)

        with pytest.raises(ValueError, match="projeto"):
            delete_sector("naval", models_dir)

        # Verify sector and projects still exist
        assert get_sector("naval", models_dir) is not None
        assert len(list_projects(models_dir)) == 2

    def test_delete_sector_with_projects_force(self, models_dir):
        """Deleting a sector with force=True deletes all projects and the sector."""
        create_sector("naval", "Naval", None, models_dir)
        p1 = create_project({"display_name": "Projeto A", "sector": "naval"}, models_dir)
        p2 = create_project({"display_name": "Projeto B", "sector": "naval"}, models_dir)

        result = delete_sector("naval", models_dir, force=True)
        assert result["deleted_sector"] == "naval"
        assert set(result["deleted_projects"]) == {p1["project_id"], p2["project_id"]}

        # Verify everything removed
        assert get_sector("naval", models_dir) is None
        assert len(list_projects(models_dir)) == 0

    def test_delete_sector_removes_all_files(self, models_dir):
        """Verify that sector_config.json, knowledge_base.json, kb_versions/ are all removed."""
        create_sector("naval", "Naval", None, models_dir)
        sector_dir = os.path.join(models_dir, "sectors", "naval")

        # Create KB and versions files to simulate a real sector
        kb_path = os.path.join(sector_dir, "knowledge_base.json")
        with open(kb_path, "w") as f:
            json.dump([{"id": "test"}], f)
        versions_dir = os.path.join(sector_dir, "kb_versions")
        os.makedirs(versions_dir, exist_ok=True)
        with open(os.path.join(versions_dir, "v1.json"), "w") as f:
            json.dump([], f)

        # Verify files exist before deletion
        assert os.path.exists(kb_path)
        assert os.path.isdir(versions_dir)

        delete_sector("naval", models_dir)

        # Verify all removed
        assert not os.path.exists(sector_dir)


