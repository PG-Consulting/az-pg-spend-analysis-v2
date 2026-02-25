"""Knowledge Base management for spend classification projects and sectors."""
import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import io

import pandas as pd
from src.utils import get_projects_dir, get_sectors_dir
from src.types import KBEntryDict, HierarchyEntryDict, KBCoverageDict, KBPaginatedDict

logger = logging.getLogger(__name__)


class KnowledgeBase:
    def __init__(self, entity_id: str, models_dir: Optional[str], entity_type: str = "project") -> None:
        self.entity_id = entity_id
        self.project_id = entity_id  # alias for backward compatibility
        self.models_dir = models_dir
        self.entity_type = entity_type

        if entity_type == "sector":
            base_dir = os.path.join(models_dir, "sectors") if models_dir else get_sectors_dir()
        else:
            base_dir = os.path.join(models_dir, "projects") if models_dir else get_projects_dir()

        self.project_dir = os.path.join(base_dir, entity_id)
        self.kb_path = os.path.join(self.project_dir, "knowledge_base.json")
        self.versions_dir = os.path.join(self.project_dir, "kb_versions")
        os.makedirs(self.versions_dir, exist_ok=True)
        self.entries = self._load()

    def _load(self) -> List[KBEntryDict]:
        if os.path.exists(self.kb_path):
            with open(self.kb_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save(self) -> None:
        with open(self.kb_path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)

    def _normalize(self, text: str) -> str:
        """Basic normalization: lowercase, strip."""
        try:
            from src.preprocessing import normalize_text
            return normalize_text(text)
        except Exception:
            return str(text).lower().strip()

    def add_entries(self, entries: List[KBEntryDict]) -> int:
        """Add entries to KB. Each entry: {description, N1, N2, N3, N4, source, confidence, instruction_used}.
        Deduplicates by description_norm only — each unique description has exactly one
        entry in the KB. When a duplicate is found, the entry is updated only if the new
        source is strictly more authoritative OR the classification (N1-N4) actually changed.
        Returns count of truly new or meaningfully updated entries."""
        # Build lookup of existing entries by description_norm only
        existing = {e["description_norm"]: i for i, e in enumerate(self.entries)}
        added = 0
        now = datetime.now(timezone.utc).isoformat()
        version = self._current_version()

        source_rank = {"consultant_correction": 2, "reclassified_with_guidance": 1, "llm_approved": 0}
        _incomplete = {"", "Não Identificado", "Nao Identificado"}

        for entry in entries:
            # Reject entries with incomplete classification
            if any(
                str(entry.get(lvl, "")).strip() in _incomplete
                for lvl in ("N1", "N2", "N3", "N4")
            ):
                continue
            desc = str(entry.get("description", ""))
            desc_norm = self._normalize(desc)
            new_source = entry.get("source", "llm_approved")

            new_entry = {
                "id": str(uuid.uuid4()),
                "description": desc,
                "description_norm": desc_norm,
                "N1": entry.get("N1", ""),
                "N2": entry.get("N2", ""),
                "N3": entry.get("N3", ""),
                "N4": entry.get("N4", ""),
                "source": new_source,
                "confidence": float(entry.get("confidence", 0.85)),
                "instruction_used": entry.get("instruction_used"),
                "version": version,
                "date_added": now,
            }

            if desc_norm in existing:
                idx = existing[desc_norm]
                old = self.entries[idx]
                old_source = old.get("source", "llm_approved")
                old_rank = source_rank.get(old_source, 0)
                new_rank = source_rank.get(new_source, 0)

                # Check if classification actually changed
                classification_changed = any(
                    old.get(f, "") != new_entry.get(f, "")
                    for f in ("N1", "N2", "N3", "N4")
                )

                # Update only if: higher authority, OR same authority with changed classification
                if new_rank > old_rank or (new_rank == old_rank and classification_changed):
                    preserved_id = old["id"]
                    self.entries[idx].update(new_entry)
                    self.entries[idx]["id"] = preserved_id  # keep old id
                    added += 1
            else:
                self.entries.append(new_entry)
                existing[desc_norm] = len(self.entries) - 1
                added += 1

        if added > 0:
            self.save()
        return added

    def update_entry(self, entry_id: str, data: Dict[str, object]) -> bool:
        for i, e in enumerate(self.entries):
            if e["id"] == entry_id:
                self.entries[i].update(data)
                self.entries[i]["id"] = entry_id  # preserve id
                self.save()
                return True
        return False

    def delete_entry(self, entry_id: str) -> bool:
        original_len = len(self.entries)
        self.entries = [e for e in self.entries if e["id"] != entry_id]
        if len(self.entries) < original_len:
            self.save()
            return True
        return False

    def search(self, query: str, limit: int = 50) -> List[KBEntryDict]:
        q = query.lower().strip()
        results = [e for e in self.entries if q in e.get("description", "").lower()]
        return results[:limit]

    def get_all(self, page: int = 1, page_size: int = 50, filters: Optional[Dict[str, str]] = None) -> KBPaginatedDict:
        entries = self.entries
        if filters:
            if filters.get("source"):
                entries = [e for e in entries if e.get("source") == filters["source"]]
            if filters.get("n1"):
                entries = [e for e in entries if e.get("N1", "").lower() == filters["n1"].lower()]
            if filters.get("n4"):
                entries = [e for e in entries if e.get("N4", "").lower() == filters["n4"].lower()]
            if filters.get("search_query"):
                q = filters["search_query"].lower()
                entries = [e for e in entries if q in e.get("description", "").lower()]

        total = len(entries)
        pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        return {"entries": entries[start:end], "total": total, "page": page, "pages": pages}

    def get_coverage(self, hierarchy: Optional[List[HierarchyEntryDict]]) -> KBCoverageDict:
        if not hierarchy:
            return {"total_n4s": 0, "covered": 0, "pct": 0.0, "underserved": []}

        all_n4s = list({entry.get("N4", "").strip() for entry in hierarchy if entry.get("N4")})
        covered_counts = {}
        for e in self.entries:
            n4 = e.get("N4", "").strip()
            covered_counts[n4] = covered_counts.get(n4, 0) + 1

        covered = sum(1 for n4 in all_n4s if covered_counts.get(n4, 0) > 0)
        underserved = [n4 for n4 in all_n4s if covered_counts.get(n4, 0) < 3]

        return {
            "total_n4s": len(all_n4s),
            "covered": covered,
            "pct": round(covered / len(all_n4s) * 100, 1) if all_n4s else 0.0,
            "underserved": sorted(underserved),
        }

    def _current_version(self) -> str:
        versions = self.list_versions()
        return f"v{len(versions) + 1}"

    def create_version_snapshot(self) -> str:
        version_id = f"v{len(self.list_versions()) + 1}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        snapshot_path = os.path.join(self.versions_dir, f"{version_id}.json")
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version_id": version_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "entry_count": len(self.entries),
                    "entries": self.entries,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        return version_id

    def rollback_to_version(self, version_id: str) -> bool:
        snapshot_path = os.path.join(self.versions_dir, f"{version_id}.json")
        if not os.path.exists(snapshot_path):
            return False
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        self.entries = snapshot.get("entries", [])
        self.save()
        return True

    def list_versions(self) -> List[Dict[str, object]]:
        versions = []
        if os.path.isdir(self.versions_dir):
            for fname in sorted(os.listdir(self.versions_dir)):
                if fname.endswith(".json"):
                    fpath = os.path.join(self.versions_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        versions.append(
                            {
                                "version_id": data.get("version_id", fname.replace(".json", "")),
                                "created_at": data.get("created_at", ""),
                                "entry_count": data.get("entry_count", 0),
                            }
                        )
                    except Exception:
                        pass
        return versions

    def export_xlsx(self) -> bytes:
        rows = []
        for e in self.entries:
            rows.append(
                {
                    "Descricao": e.get("description", ""),
                    "N1": e.get("N1", ""),
                    "N2": e.get("N2", ""),
                    "N3": e.get("N3", ""),
                    "N4": e.get("N4", ""),
                    "Fonte": e.get("source", ""),
                    "Confianca": e.get("confidence", ""),
                    "Data": e.get("date_added", ""),
                    "Instrucao": e.get("instruction_used", ""),
                }
            )
        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="KnowledgeBase")
        return buf.getvalue()

    def import_xlsx(self, file_bytes: bytes) -> Dict[str, int]:
        df = pd.read_excel(io.BytesIO(file_bytes))
        entries = []
        for _, row in df.iterrows():
            entries.append(
                {
                    "description": str(row.get("Descricao", row.get("description", ""))),
                    "N1": str(row.get("N1", "")),
                    "N2": str(row.get("N2", "")),
                    "N3": str(row.get("N3", "")),
                    "N4": str(row.get("N4", "")),
                    "source": str(row.get("Fonte", row.get("source", "consultant_correction"))),
                    "confidence": float(row.get("Confianca", row.get("confidence", 1.0))),
                    "instruction_used": row.get("Instrucao", row.get("instruction_used")),
                }
            )
        added = self.add_entries(entries)
        return {"added": added, "total": len(self.entries)}

    def seed_from_project(self, source_project_id: str) -> int:
        """Deprecated: use sector KB + merge_kb_entries() instead."""
        logger.warning(
            "seed_from_project() is deprecated. Use sector KB + merge_kb_entries() instead."
        )
        source_kb_path = os.path.join(
            os.path.dirname(self.project_dir), source_project_id, "knowledge_base.json"
        )
        if not os.path.exists(source_kb_path):
            return 0
        with open(source_kb_path, "r", encoding="utf-8") as f:
            source_entries = json.load(f)

        entries_to_add = []
        for e in source_entries:
            entries_to_add.append(
                {
                    "description": e.get("description", ""),
                    "N1": e.get("N1", ""),
                    "N2": e.get("N2", ""),
                    "N3": e.get("N3", ""),
                    "N4": e.get("N4", ""),
                    "source": e.get("source", "llm_approved"),
                    "confidence": e.get("confidence", 0.85),
                    "instruction_used": e.get("instruction_used"),
                }
            )
        return self.add_entries(entries_to_add)

    def promote_entries_to(self, target_kb: 'KnowledgeBase', entry_ids: List[str]) -> int:
        """Promote selected entries from this KB to the target KB.

        Filters entries by IDs, creates a snapshot on the target before adding,
        then calls target_kb.add_entries() (dedup is automatic).
        Returns count of entries added/updated in target.
        """
        entries_to_promote = [e for e in self.entries if e.get("id") in set(entry_ids)]
        if not entries_to_promote:
            return 0

        target_kb.create_version_snapshot()

        add_list = []
        for e in entries_to_promote:
            add_list.append({
                "description": e.get("description", ""),
                "N1": e.get("N1", ""),
                "N2": e.get("N2", ""),
                "N3": e.get("N3", ""),
                "N4": e.get("N4", ""),
                "source": e.get("source", "llm_approved"),
                "confidence": e.get("confidence", 0.85),
                "instruction_used": e.get("instruction_used"),
            })

        return target_kb.add_entries(add_list)


def merge_kb_entries(sector_entries: List[KBEntryDict], project_entries: List[KBEntryDict]) -> List[KBEntryDict]:
    """Merge sector + project KB entries. Project overrides sector by description_norm.

    Uses description_norm as the merge key. Sector entries are added first,
    then project entries override any matching sector entries.
    Returns a new list (does not mutate inputs).
    """
    merged = {}
    for entry in sector_entries:
        key = entry.get("description_norm", "")
        if key:
            merged[key] = entry
    for entry in project_entries:
        key = entry.get("description_norm", "")
        if key:
            merged[key] = entry
    return list(merged.values())
