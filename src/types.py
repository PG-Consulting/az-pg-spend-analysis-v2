"""TypedDict definitions for core data structures used across the spend analysis pipeline.

These types are runtime-inert -- they exist solely for static type checking and
editor autocompletion. They mirror the actual dict shapes found in knowledge_base.json,
status.json, classification results, hierarchy entries, and KB retriever output.
"""

from typing import List, Literal, Optional, TypedDict


# ---------------------------------------------------------------------------
# Source and status literals
# ---------------------------------------------------------------------------

KBSourceLiteral = Literal[
    "llm_approved",
    "consultant_correction",
    "reclassified_with_guidance",
]

ClassificationSourceLiteral = Literal[
    "KB (Direct Match)",
    "LLM (Batch)",
    "LLM (Reclassified)",
    "Taxonomy (Dict)",
    "ML",
    "None",
]

JobStatusLiteral = Literal[
    "PENDING",
    "PROCESSING",
    "CLASSIFIED",
    "APPROVED",
    "COMPLETED",
    "ERROR",
    "CANCELLED",
]


# ---------------------------------------------------------------------------
# KBEntryDict -- knowledge_base.json entries
# ---------------------------------------------------------------------------

class _KBEntryRequired(TypedDict):
    id: str
    description: str
    description_norm: str
    N1: str
    N2: str
    N3: str
    N4: str
    source: str  # KBSourceLiteral at runtime, kept str for flexibility
    confidence: float


class KBEntryDict(_KBEntryRequired, total=False):
    """Full KB entry as stored in knowledge_base.json.

    Required fields are always present after ``add_entries()``; optional fields
    may be absent on older entries or entries created via import.
    """
    instruction_used: Optional[str]
    version: str
    date_added: str


# ---------------------------------------------------------------------------
# ClassificationResultDict -- output of the classification pipeline
# ---------------------------------------------------------------------------

class _ClassificationResultRequired(TypedDict):
    description: str
    N1: str
    N2: str
    N3: str
    N4: str
    source: str  # ClassificationSourceLiteral
    confidence: float


class ClassificationResultDict(_ClassificationResultRequired, total=False):
    """Single classification result returned by ``process_dataframe_chunk()``.

    The legacy ML path may also include ``status`` and ``matched_terms``;
    the LLM-direct path omits those fields.
    """
    status: str
    matched_terms: List[str]


# ---------------------------------------------------------------------------
# HierarchyEntryDict -- N1/N2/N3/N4 hierarchy row
# ---------------------------------------------------------------------------

class HierarchyEntryDict(TypedDict):
    """Single row from a custom hierarchy file (parsed from Excel).

    Stored as a list -- not a dict -- to preserve duplicate N4 values
    across different N1/N2/N3 branches.
    """
    N1: str
    N2: str
    N3: str
    N4: str


# ---------------------------------------------------------------------------
# JobStatusDict -- status.json for a taxonomy job
# ---------------------------------------------------------------------------

class _JobStatusRequired(TypedDict):
    job_id: str
    created_at: str
    status: JobStatusLiteral
    sector: str
    filename: str
    desc_column: str
    total_rows: int
    total_chunks: int
    processed_chunks: int


class JobStatusDict(_JobStatusRequired, total=False):
    """Full job status as stored in ``taxonomy_jobs/<job_id>/status.json``.

    Optional fields depend on the submission path (project vs. legacy)
    and on the job lifecycle stage (e.g. ``error`` is only set on ERROR).
    """
    client_context: str
    project_id: Optional[str]
    custom_hierarchy_b64: Optional[str]
    custom_hierarchy_list: Optional[List[HierarchyEntryDict]]
    dictionary_content_b64: Optional[str]
    error: str


# ---------------------------------------------------------------------------
# KBRetrieveMatchDict -- KB entry augmented with similarity score
# ---------------------------------------------------------------------------

class KBRetrieveMatchDict(KBEntryDict, total=False):
    """KB entry returned by ``KBRetriever.retrieve()`` / ``retrieve_batch()``.

    Inherits all ``KBEntryDict`` fields plus a ``_similarity`` score computed
    via TF-IDF cosine similarity. The ``_similarity`` key is stripped by
    ``select_enriched_examples()`` before the entries are sent to the LLM.
    """
    _similarity: float


# ---------------------------------------------------------------------------
# Auxiliary dicts (KB coverage, pagination)
# ---------------------------------------------------------------------------

class KBCoverageDict(TypedDict):
    """Coverage statistics returned by ``KnowledgeBase.get_coverage()``."""
    total_n4s: int
    covered: int
    pct: float
    underserved: List[str]


class KBPaginatedDict(TypedDict):
    """Paginated response returned by ``KnowledgeBase.get_all()``."""
    entries: List[KBEntryDict]
    total: int
    page: int
    pages: int


# ---------------------------------------------------------------------------
# JobInfoDict -- worker internal dict passed between helper functions
# ---------------------------------------------------------------------------

class _JobInfoRequired(TypedDict):
    job_id: str
    job_dir: str
    status_path: str
    status: dict
    total_chunks: int


class JobInfoDict(_JobInfoRequired, total=False):
    """Worker-internal dict that bundles job metadata, parsed hierarchy,
    and pre-built KB retriever for reuse across chunks.

    Built by ``get_active_jobs()`` and consumed by ``process_single_chunk()``,
    ``update_job_progress()``, and ``consolidate_job()``.
    """
    custom_hierarchy: Optional[List[HierarchyEntryDict]]
    hierarchy_lookup: object
    kb_entries: List[KBEntryDict]
    kb_retriever: object
