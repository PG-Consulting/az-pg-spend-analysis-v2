"""Tests for src.knowledge_base.KnowledgeBase."""

import json
import pytest
from src.knowledge_base import KnowledgeBase, merge_kb_entries


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_kb(tmp_path, project_id="test-project", initial_entries=None):
    """Create a KnowledgeBase instance backed by a temp directory."""
    project_dir = tmp_path / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    if initial_entries:
        kb_path = project_dir / "knowledge_base.json"
        kb_path.write_text(json.dumps(initial_entries, ensure_ascii=False))
    return KnowledgeBase(project_id, str(tmp_path))


def _entry(description, n4, source="llm_approved", confidence=0.85, **kwargs):
    """Shorthand for building an entry dict."""
    return {
        "description": description,
        "N1": kwargs.get("N1", "MRO"),
        "N2": kwargs.get("N2", "Geral"),
        "N3": kwargs.get("N3", "Geral"),
        "N4": n4,
        "source": source,
        "confidence": confidence,
        "instruction_used": kwargs.get("instruction_used"),
    }


# ---------------------------------------------------------------------------
# Tests: initialization
# ---------------------------------------------------------------------------

class TestKBInit:
    def test_init_empty(self, tmp_path):
        """New KB with no pre-existing file starts with empty entries."""
        kb = make_kb(tmp_path)
        assert kb.entries == []

    def test_init_existing(self, tmp_path):
        """KB loads existing entries from file on disk."""
        initial = [
            {
                "id": "aaa",
                "description": "Parafuso",
                "description_norm": "parafuso",
                "N1": "MRO",
                "N2": "Fixacao",
                "N3": "Parafusos",
                "N4": "Parafuso Sextavado",
                "source": "llm_approved",
                "confidence": 0.9,
                "version": "v1",
                "date_added": "2026-02-18T00:00:00",
            }
        ]
        kb = make_kb(tmp_path, initial_entries=initial)
        assert len(kb.entries) == 1
        assert kb.entries[0]["id"] == "aaa"


# ---------------------------------------------------------------------------
# Tests: add_entries
# ---------------------------------------------------------------------------

class TestKBAddEntries:
    def test_add_entries_basic(self, tmp_path):
        """Adding 3 distinct entries returns count=3 and persists them."""
        kb = make_kb(tmp_path)
        entries = [
            _entry("Parafuso Sextavado M8", "Parafuso Sextavado"),
            _entry("Óleo Lubrificante Motor", "Óleo Motor"),
            _entry("Filtro de Ar Compressor", "Filtro de Ar"),
        ]
        added = kb.add_entries(entries)
        assert added == 3
        assert len(kb.entries) == 3

        # Verify persistence: reload from disk
        kb2 = make_kb(tmp_path)
        assert len(kb2.entries) == 3

    def test_add_entries_dedup(self, tmp_path):
        """Same description_norm is not duplicated."""
        kb = make_kb(tmp_path)
        entry = _entry("Parafuso Sextavado M8", "Parafuso Sextavado")
        kb.add_entries([entry])
        kb.add_entries([entry])  # add same again

        assert len(kb.entries) == 1

    def test_add_entries_dedup_different_n4(self, tmp_path):
        """Same description with different N4 updates in-place (no duplicate)."""
        kb = make_kb(tmp_path)
        kb.add_entries([_entry("Parafuso Sextavado M8", "Parafuso Sextavado")])
        assert kb.entries[0]["N4"] == "Parafuso Sextavado"

        # Re-add same description but classified with different N4
        kb.add_entries([_entry("Parafuso Sextavado M8", "Fixadores Metálicos")])
        assert len(kb.entries) == 1  # no duplicate
        assert kb.entries[0]["N4"] == "Fixadores Metálicos"  # updated to latest

    def test_add_identical_entries_twice_returns_zero(self, tmp_path):
        """Approving the exact same items twice returns kb_added=0 the second time."""
        kb = make_kb(tmp_path)
        entries = [
            _entry("Parafuso Sextavado M8", "Parafuso Sextavado"),
            _entry("Óleo Lubrificante Motor", "Óleo Motor"),
        ]
        first_added = kb.add_entries(entries)
        assert first_added == 2
        assert len(kb.entries) == 2

        # Re-approve identical items — nothing should change
        second_added = kb.add_entries(entries)
        assert second_added == 0
        assert len(kb.entries) == 2

    def test_add_entries_consultant_overwrites_llm(self, tmp_path):
        """consultant_correction overwrites llm_approved for the same key."""
        kb = make_kb(tmp_path)

        llm_entry = _entry("Parafuso Sextavado M8", "Parafuso Sextavado", source="llm_approved")
        kb.add_entries([llm_entry])
        assert kb.entries[0]["source"] == "llm_approved"

        consultant_entry = _entry(
            "Parafuso Sextavado M8", "Parafuso Sextavado",
            source="consultant_correction", confidence=1.0,
        )
        added = kb.add_entries([consultant_entry])
        assert added == 1
        assert len(kb.entries) == 1
        assert kb.entries[0]["source"] == "consultant_correction"
        assert kb.entries[0]["confidence"] == 1.0

    def test_add_entries_llm_does_not_overwrite_consultant(self, tmp_path):
        """llm_approved does NOT overwrite an existing consultant_correction entry."""
        kb = make_kb(tmp_path)

        consultant_entry = _entry(
            "Parafuso Sextavado M8", "Parafuso Sextavado",
            source="consultant_correction", confidence=1.0,
        )
        kb.add_entries([consultant_entry])
        assert kb.entries[0]["source"] == "consultant_correction"

        llm_entry = _entry(
            "Parafuso Sextavado M8", "Parafuso Sextavado",
            source="llm_approved", confidence=0.7,
        )
        added = kb.add_entries([llm_entry])
        assert added == 0  # nothing added/overwritten
        assert len(kb.entries) == 1
        assert kb.entries[0]["source"] == "consultant_correction"
        assert kb.entries[0]["confidence"] == 1.0

    def test_add_entries_rejects_nao_identificado_n4(self, tmp_path):
        """Entries with N4='Não Identificado' are silently rejected."""
        kb = make_kb(tmp_path)
        entry = _entry("Servico Transporte Pessoas", "Não Identificado")
        added = kb.add_entries([entry])
        assert added == 0
        assert len(kb.entries) == 0

    def test_add_entries_rejects_empty_n1(self, tmp_path):
        """Entries with empty N1 are silently rejected."""
        kb = make_kb(tmp_path)
        entry = {
            "description": "Algo",
            "N1": "",
            "N2": "Geral",
            "N3": "Geral",
            "N4": "Algo N4",
            "source": "llm_approved",
            "confidence": 0.85,
        }
        added = kb.add_entries([entry])
        assert added == 0
        assert len(kb.entries) == 0

    def test_add_entries_accepts_complete_classification(self, tmp_path):
        """Entries with all N1-N4 filled are accepted normally."""
        kb = make_kb(tmp_path)
        entry = _entry("Parafuso Sextavado M8", "Parafuso Sextavado")
        added = kb.add_entries([entry])
        assert added == 1
        assert len(kb.entries) == 1


# ---------------------------------------------------------------------------
# Tests: delete_entry
# ---------------------------------------------------------------------------

class TestKBDelete:
    def test_delete_entry(self, tmp_path):
        """Deleting by ID removes the entry and persists."""
        kb = make_kb(tmp_path)
        kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])
        entry_id = kb.entries[0]["id"]

        result = kb.delete_entry(entry_id)
        assert result is True
        assert len(kb.entries) == 0

        # Verify persistence
        kb2 = make_kb(tmp_path)
        assert len(kb2.entries) == 0

    def test_delete_nonexistent(self, tmp_path):
        """Deleting a nonexistent ID returns False."""
        kb = make_kb(tmp_path)
        result = kb.delete_entry("nonexistent-id")
        assert result is False


# ---------------------------------------------------------------------------
# Tests: update_entry
# ---------------------------------------------------------------------------

class TestKBUpdate:
    def test_update_entry(self, tmp_path):
        """Update N1 of an existing entry."""
        kb = make_kb(tmp_path)
        kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado", N1="MRO")])
        entry_id = kb.entries[0]["id"]

        result = kb.update_entry(entry_id, {"N1": "Materiais"})
        assert result is True
        assert kb.entries[0]["N1"] == "Materiais"
        # ID should be preserved
        assert kb.entries[0]["id"] == entry_id

    def test_update_nonexistent(self, tmp_path):
        """Updating a nonexistent entry returns False."""
        kb = make_kb(tmp_path)
        result = kb.update_entry("nonexistent-id", {"N1": "Materiais"})
        assert result is False


# ---------------------------------------------------------------------------
# Tests: search
# ---------------------------------------------------------------------------

class TestKBSearch:
    def test_search(self, tmp_path):
        """search('parafuso') finds matching entries."""
        kb = make_kb(tmp_path)
        kb.add_entries([
            _entry("Parafuso Sextavado M8", "Parafuso Sextavado"),
            _entry("Óleo Lubrificante Motor", "Óleo Motor"),
            _entry("Parafuso Allen M6", "Parafuso Allen"),
        ])
        results = kb.search("parafuso")
        assert len(results) == 2

    def test_search_no_results(self, tmp_path):
        """search('xyz') returns empty list when nothing matches."""
        kb = make_kb(tmp_path)
        kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])
        results = kb.search("xyz")
        assert results == []


# ---------------------------------------------------------------------------
# Tests: get_all (pagination and filters)
# ---------------------------------------------------------------------------

class TestKBGetAll:
    def test_get_all_pagination(self, tmp_path):
        """15 entries with page_size=5 produces 3 pages."""
        kb = make_kb(tmp_path)
        entries = [_entry(f"Item {i}", f"Cat {i}") for i in range(15)]
        kb.add_entries(entries)

        page1 = kb.get_all(page=1, page_size=5)
        assert page1["total"] == 15
        assert page1["pages"] == 3
        assert page1["page"] == 1
        assert len(page1["entries"]) == 5

        page3 = kb.get_all(page=3, page_size=5)
        assert len(page3["entries"]) == 5

    def test_get_all_filter_source(self, tmp_path):
        """Filtering by source returns only matching entries."""
        kb = make_kb(tmp_path)
        kb.add_entries([
            _entry("Item A", "Cat A", source="llm_approved"),
            _entry("Item B", "Cat B", source="consultant_correction"),
            _entry("Item C", "Cat C", source="llm_approved"),
        ])
        result = kb.get_all(filters={"source": "consultant_correction"})
        assert result["total"] == 1
        assert result["entries"][0]["source"] == "consultant_correction"


# ---------------------------------------------------------------------------
# Tests: get_coverage
# ---------------------------------------------------------------------------

class TestKBCoverage:
    def test_get_coverage(self, tmp_path):
        """With a hierarchy, calculates covered N4s."""
        hierarchy = [
            {"N1": "MRO", "N2": "Fixação", "N3": "Parafusos", "N4": "Parafuso Sextavado"},
            {"N1": "MRO", "N2": "Lubrificação", "N3": "Óleos", "N4": "Óleo Motor"},
            {"N1": "MRO", "N2": "Filtração", "N3": "Filtros", "N4": "Filtro de Ar"},
        ]
        kb = make_kb(tmp_path)
        kb.add_entries([
            _entry("Parafuso M8", "Parafuso Sextavado"),
            _entry("Óleo Motor", "Óleo Motor"),
        ])

        coverage = kb.get_coverage(hierarchy)
        assert coverage["total_n4s"] == 3
        assert coverage["covered"] == 2
        assert coverage["pct"] == pytest.approx(66.7, abs=0.1)
        # "Filtro de Ar" has <3 entries, so it's underserved
        assert "Filtro de Ar" in coverage["underserved"]

    def test_get_coverage_no_hierarchy(self, tmp_path):
        """Without hierarchy (None), returns zeros."""
        kb = make_kb(tmp_path)
        coverage = kb.get_coverage(None)
        assert coverage["total_n4s"] == 0
        assert coverage["covered"] == 0
        assert coverage["pct"] == 0.0


# ---------------------------------------------------------------------------
# Tests: versioning
# ---------------------------------------------------------------------------

class TestKBVersioning:
    def test_create_version_snapshot(self, tmp_path):
        """Creating a snapshot produces a version file on disk."""
        kb = make_kb(tmp_path)
        kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])

        version_id = kb.create_version_snapshot()
        assert version_id  # non-empty string

        # Verify snapshot file exists
        import os
        snapshot_path = os.path.join(kb.versions_dir, f"{version_id}.json")
        assert os.path.exists(snapshot_path)

        # Verify snapshot content
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        assert snapshot["entry_count"] == 1
        assert len(snapshot["entries"]) == 1

    def test_rollback_to_version(self, tmp_path):
        """Create snapshot, add more entries, then rollback restores old state."""
        kb = make_kb(tmp_path)
        kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])
        assert len(kb.entries) == 1

        version_id = kb.create_version_snapshot()

        # Add more entries after snapshot
        kb.add_entries([
            _entry("Óleo Motor", "Óleo Motor"),
            _entry("Filtro Ar", "Filtro de Ar"),
        ])
        assert len(kb.entries) == 3

        # Rollback
        result = kb.rollback_to_version(version_id)
        assert result is True
        assert len(kb.entries) == 1
        assert kb.entries[0]["N4"] == "Parafuso Sextavado"

        # Verify persistence after rollback
        kb2 = make_kb(tmp_path)
        assert len(kb2.entries) == 1

    def test_rollback_nonexistent_version(self, tmp_path):
        """Rollback to a nonexistent version returns False."""
        kb = make_kb(tmp_path)
        result = kb.rollback_to_version("v999_nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# Helper for sector KB
# ---------------------------------------------------------------------------

def make_sector_kb(tmp_path, sector_name="test-sector", initial_entries=None):
    """Create a KnowledgeBase instance for a sector backed by a temp directory."""
    sector_dir = tmp_path / "sectors" / sector_name
    sector_dir.mkdir(parents=True, exist_ok=True)
    if initial_entries:
        kb_path = sector_dir / "knowledge_base.json"
        kb_path.write_text(json.dumps(initial_entries, ensure_ascii=False))
    return KnowledgeBase(sector_name, str(tmp_path), entity_type="sector")


# ---------------------------------------------------------------------------
# Tests: Sector KB (entity_type="sector")
# ---------------------------------------------------------------------------

class TestSectorKB:
    def test_sector_kb_init_empty(self, tmp_path):
        """New sector KB starts empty."""
        kb = make_sector_kb(tmp_path)
        assert kb.entries == []
        assert kb.entity_type == "sector"

    def test_sector_kb_add_and_load(self, tmp_path):
        """Sector KB persists entries to sector directory."""
        kb = make_sector_kb(tmp_path)
        kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])
        assert len(kb.entries) == 1

        # Reload from disk
        kb2 = make_sector_kb(tmp_path)
        assert len(kb2.entries) == 1

    def test_sector_kb_versioning(self, tmp_path):
        """Sector KB supports versioning like project KB."""
        kb = make_sector_kb(tmp_path)
        kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])
        version_id = kb.create_version_snapshot()
        assert version_id

        kb.add_entries([_entry("Óleo Motor", "Óleo Motor")])
        assert len(kb.entries) == 2

        result = kb.rollback_to_version(version_id)
        assert result is True
        assert len(kb.entries) == 1

    def test_sector_kb_path_is_in_sectors_dir(self, tmp_path):
        """Sector KB path should be in sectors/ subdirectory, not projects/."""
        kb = make_sector_kb(tmp_path, "naval")
        assert "sectors/naval" in kb.kb_path
        assert "projects" not in kb.kb_path

    def test_sector_kb_uses_sectors_dir(self, tmp_path):
        """Verify sector KB resolves to the correct sectors/ directory."""
        kb = make_sector_kb(tmp_path, "petroleo")
        assert "sectors/petroleo" in kb.kb_path
        kb.add_entries([_entry("Valvula Gaveta", "Valvula Gaveta")])
        import os
        assert os.path.exists(os.path.join(str(tmp_path), "sectors", "petroleo", "knowledge_base.json"))

    def test_sector_kb_update_entry(self, tmp_path):
        """Sector KB update_entry works correctly."""
        kb = make_sector_kb(tmp_path)
        kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado", N1="MRO")])
        entry_id = kb.entries[0]["id"]

        result = kb.update_entry(entry_id, {"N1": "Materiais", "N4": "Parafuso Allen"})
        assert result is True
        assert kb.entries[0]["N1"] == "Materiais"
        assert kb.entries[0]["N4"] == "Parafuso Allen"

        # Verify persistence
        kb2 = make_sector_kb(tmp_path)
        assert kb2.entries[0]["N1"] == "Materiais"

    def test_sector_kb_delete_entry(self, tmp_path):
        """Sector KB delete_entry removes and persists."""
        kb = make_sector_kb(tmp_path)
        kb.add_entries([
            _entry("Parafuso M8", "Parafuso Sextavado"),
            _entry("Oleo Motor", "Oleo Motor"),
        ])
        assert len(kb.entries) == 2

        entry_id = kb.entries[0]["id"]
        result = kb.delete_entry(entry_id)
        assert result is True
        assert len(kb.entries) == 1

        # Verify persistence
        kb2 = make_sector_kb(tmp_path)
        assert len(kb2.entries) == 1

    def test_sector_kb_rollback(self, tmp_path):
        """Sector KB rollback restores previous state."""
        kb = make_sector_kb(tmp_path)
        kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])
        version_id = kb.create_version_snapshot()

        kb.add_entries([_entry("Oleo Motor", "Oleo Motor")])
        assert len(kb.entries) == 2

        result = kb.rollback_to_version(version_id)
        assert result is True
        assert len(kb.entries) == 1
        assert kb.entries[0]["N4"] == "Parafuso Sextavado"

        # Verify persistence after rollback
        kb2 = make_sector_kb(tmp_path)
        assert len(kb2.entries) == 1


# ---------------------------------------------------------------------------
# Tests: merge_kb_entries
# ---------------------------------------------------------------------------

class TestMergeKBEntries:
    def test_merge_empty(self):
        """Merging two empty lists returns empty."""
        result = merge_kb_entries([], [])
        assert result == []

    def test_merge_project_overrides_sector(self):
        """Project entry overrides sector entry with same description_norm."""
        sector_entries = [
            {"description_norm": "parafuso m8", "N4": "Sector Cat", "id": "s1"},
        ]
        project_entries = [
            {"description_norm": "parafuso m8", "N4": "Project Cat", "id": "p1"},
        ]
        result = merge_kb_entries(sector_entries, project_entries)
        assert len(result) == 1
        assert result[0]["N4"] == "Project Cat"
        assert result[0]["id"] == "p1"

    def test_merge_non_overlapping(self):
        """Non-overlapping entries from both are preserved."""
        sector_entries = [
            {"description_norm": "parafuso m8", "N4": "Cat A", "id": "s1"},
        ]
        project_entries = [
            {"description_norm": "oleo motor", "N4": "Cat B", "id": "p1"},
        ]
        result = merge_kb_entries(sector_entries, project_entries)
        assert len(result) == 2
        norms = {e["description_norm"] for e in result}
        assert norms == {"parafuso m8", "oleo motor"}

    def test_merge_does_not_mutate_inputs(self):
        """merge_kb_entries should not mutate the input lists."""
        sector = [{"description_norm": "a", "id": "s1"}]
        project = [{"description_norm": "b", "id": "p1"}]
        original_sector_len = len(sector)
        original_project_len = len(project)
        merge_kb_entries(sector, project)
        assert len(sector) == original_sector_len
        assert len(project) == original_project_len

    def test_merge_sector_only(self):
        """When project is empty, sector entries are returned."""
        sector_entries = [
            {"description_norm": "parafuso m8", "N4": "Cat A", "id": "s1"},
            {"description_norm": "oleo motor", "N4": "Cat B", "id": "s2"},
        ]
        result = merge_kb_entries(sector_entries, [])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests: promote_entries_to
# ---------------------------------------------------------------------------

class TestPromoteEntries:
    def test_promote_entries(self, tmp_path):
        """Promoting entries from project KB to sector KB adds them to the sector."""
        project_kb = make_kb(tmp_path)
        project_kb.add_entries([
            _entry("Parafuso M8", "Parafuso Sextavado"),
            _entry("Óleo Motor", "Óleo Motor"),
            _entry("Filtro Ar", "Filtro de Ar"),
        ])
        assert len(project_kb.entries) == 3

        sector_kb = make_sector_kb(tmp_path)
        assert len(sector_kb.entries) == 0

        entry_ids = [project_kb.entries[0]["id"], project_kb.entries[2]["id"]]
        promoted = project_kb.promote_entries_to(sector_kb, entry_ids)
        assert promoted == 2
        assert len(sector_kb.entries) == 2

    def test_promote_empty_ids(self, tmp_path):
        """Promoting with empty IDs returns 0."""
        project_kb = make_kb(tmp_path)
        project_kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])
        sector_kb = make_sector_kb(tmp_path)
        promoted = project_kb.promote_entries_to(sector_kb, [])
        assert promoted == 0

    def test_promote_nonexistent_ids(self, tmp_path):
        """Promoting with IDs that don't exist returns 0."""
        project_kb = make_kb(tmp_path)
        project_kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])
        sector_kb = make_sector_kb(tmp_path)
        promoted = project_kb.promote_entries_to(sector_kb, ["nonexistent-id"])
        assert promoted == 0

    def test_promote_creates_snapshot(self, tmp_path):
        """Promoting entries creates a version snapshot on the target."""
        project_kb = make_kb(tmp_path)
        project_kb.add_entries([_entry("Parafuso M8", "Parafuso Sextavado")])

        sector_kb = make_sector_kb(tmp_path)
        entry_ids = [project_kb.entries[0]["id"]]
        project_kb.promote_entries_to(sector_kb, entry_ids)

        versions = sector_kb.list_versions()
        assert len(versions) >= 1
