"""
Worker helper functions for the async taxonomy classification job queue.

These are extracted from the monolithic function_app.py (v2) and adapted for the
new-solution architecture:
- Function names are public (no leading underscore).
- get_active_jobs() loads the project Knowledge Base (KB) for each job.
- process_single_chunk() passes KB entries and project_id to process_dataframe_chunk().
- consolidate_job() sets final status to "CLASSIFIED" (not "COMPLETED") so that a
  human review step can follow before the job is considered fully done.
- Model directory resolution uses src.utils.get_models_dir().
"""

import os
import io
import json
import base64
import logging
import time
import glob as glob_mod
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from typing import Dict, List, Optional, Set

from src.types import HierarchyEntryDict, JobInfoDict
from src.utils import (
    get_jobs_dir,
    get_models_dir,
    friendly_source_label,
    safe_json_dumps,
    INCOMPLETE_VALUES,
)
from src.project_manager import get_project
from src.file_lock import read_status, update_status, locked_status

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALE_THRESHOLD_SECONDS = 3600  # 1 hour - jobs PROCESSING beyond this become ERROR
MAX_PARALLEL_CHUNKS = 5  # Max simultaneous chunks across all active jobs


# ---------------------------------------------------------------------------
# handle_poison_message
# ---------------------------------------------------------------------------


def handle_poison_message(job_id: str) -> None:
    """Mark a job as ERROR after exhausting queue retries (poison queue)."""
    jobs_root = get_jobs_dir()
    job_dir = os.path.join(jobs_root, job_id)
    status_path = os.path.join(job_dir, "status.json")

    if not os.path.exists(status_path):
        logger.warning(f"[PoisonHandler] Job {job_id} não encontrado")
        return

    # Pre-check: avoid acquiring write lock if no mutation needed
    _TERMINAL = ("CANCELLED", "COMPLETED", "CLASSIFIED", "APPROVED", "ERROR")
    current = read_status(status_path).get("status", "")
    if current in _TERMINAL:
        logger.info(f"[PoisonHandler] Job {job_id} já em '{current}' — ignorando")
        return

    with locked_status(status_path) as data:
        # Re-check inside lock (status could have changed)
        if data.get("status", "") in _TERMINAL:
            return
        data["status"] = "ERROR"
        data["error"] = (
            "Job falhou após múltiplas tentativas de processamento (poison queue). "
            "Verifique os logs do worker para detalhes."
        )
        data["error_at"] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# cleanup_stale_jobs
# ---------------------------------------------------------------------------


def cleanup_stale_jobs(jobs_root: str) -> None:
    """Mark PROCESSING jobs older than 1 hour as ERROR (auto-cleanup)."""
    for job_id in os.listdir(jobs_root):
        job_dir = os.path.join(jobs_root, job_id)
        status_path = os.path.join(job_dir, "status.json")
        if not os.path.isdir(job_dir) or not os.path.exists(status_path):
            continue
        try:
            status = read_status(status_path)
            if status.get("status") != "PROCESSING":
                continue
            created_at = status.get("created_at")
            if not created_at:
                continue
            created_dt = datetime.fromisoformat(created_at)
            elapsed = (datetime.now(timezone.utc) - created_dt).total_seconds()
            if elapsed > STALE_THRESHOLD_SECONDS:
                # Atomic check-and-set: only mark ERROR if still PROCESSING
                with locked_status(status_path) as data:
                    if data.get("status") != "PROCESSING":
                        continue
                    logger.warning(
                        f"[Worker] Job {job_id} stuck for {elapsed / 60:.0f}min. Marking as ERROR."
                    )
                    data["status"] = "ERROR"
                    data["error"] = (
                        f"Job expired after {elapsed / 60:.0f} minutes without completing"
                    )
        except Exception as e:
            logger.error(f"[Worker] Error checking stale job {job_id}: {e}")


# ---------------------------------------------------------------------------
# get_active_jobs
# ---------------------------------------------------------------------------


def _prepare_job_info(
    job_id: str,
    job_dir: str,
    status_path: str,
    status: Dict[str, object],
) -> JobInfoDict:
    """Build a JobInfoDict with parsed hierarchy, merged KB, and KBRetriever.

    Shared helper used by both get_active_jobs() and process_single_job().
    """
    models_dir = get_models_dir()

    # Parse hierarchy once per job (avoids re-decoding base64+Excel per chunk)
    custom_hierarchy = parse_custom_hierarchy(status)
    hierarchy_lookup = None
    if custom_hierarchy:
        from src.hierarchy_validator import HierarchyLookup

        hierarchy_lookup = HierarchyLookup(custom_hierarchy)

    # Load KB for few-shot retrieval (sector + project merged)
    from src.knowledge_base import KnowledgeBase, merge_kb_entries

    project_id = status.get("project_id")
    if project_id:
        try:
            project_kb = KnowledgeBase(project_id, models_dir)
            project_config = get_project(project_id, models_dir)
            sector_slug = project_config.get("sector", "") if project_config else ""
            sector_entries = []
            use_sector_kb = (
                project_config.get("use_sector_kb", True) if project_config else True
            )
            if sector_slug and use_sector_kb:
                try:
                    sector_kb = KnowledgeBase(
                        sector_slug, models_dir, entity_type="sector"
                    )
                    sector_entries = sector_kb.entries
                except Exception:
                    pass
            kb_entries = merge_kb_entries(sector_entries, project_kb.entries)
        except Exception as e:
            logger.warning(f"Could not load KB for project {project_id}: {e}")
            kb_entries = []
    else:
        kb_entries = []

    # Create KBRetriever indexed once per job (reused across all chunks)
    from src.kb_retriever import KBRetriever

    kb_retriever = KBRetriever(kb_entries) if kb_entries else None

    return {
        "job_id": job_id,
        "job_dir": job_dir,
        "status_path": status_path,
        "status": status,
        "total_chunks": status["total_chunks"],
        "custom_hierarchy": custom_hierarchy,
        "hierarchy_lookup": hierarchy_lookup,
        "kb_entries": kb_entries,
        "kb_retriever": kb_retriever,
    }


# ---------------------------------------------------------------------------
# find_next_chunks
# ---------------------------------------------------------------------------


def find_next_chunks(
    job_info: JobInfoDict, max_count: int = 1, exclude: Optional[Set[int]] = None
) -> List[int]:
    """Return up to max_count unprocessed chunk indices (excluding already-assigned ones)."""
    if exclude is None:
        exclude = set()
    job_dir = job_info["job_dir"]
    chunks = []
    for i in range(job_info["total_chunks"]):
        if len(chunks) >= max_count:
            break
        if i in exclude:
            continue
        chunk_file = os.path.join(job_dir, f"chunk_{i}.json")
        result_file = os.path.join(job_dir, f"result_{i}.json")
        if os.path.exists(chunk_file) and not os.path.exists(result_file):
            chunks.append(i)
    return chunks


# ---------------------------------------------------------------------------
# parse_custom_hierarchy
# ---------------------------------------------------------------------------


def parse_custom_hierarchy(
    status: Dict[str, object],
) -> Optional[List[HierarchyEntryDict]]:
    """
    Resolve the custom hierarchy from job status.

    Priority:
      1. custom_hierarchy_b64 (per-job Excel upload — always overrides)
      2. custom_hierarchy_list (from project config — already parsed as list of dicts)
      3. None (open classification, no hierarchy constraint)

    For b64 path: robust header detection (N1,N2,N3,N4) even with blank rows above.
    Returns a list of dicts (preserves duplicate N4 names across different N3 branches).
    """
    import pandas as pd

    # Path 2: project-based hierarchy already stored as list of dicts
    hierarchy_list = status.get("custom_hierarchy_list")
    if hierarchy_list and isinstance(hierarchy_list, list) and len(hierarchy_list) > 0:
        logger.info(
            f"Custom hierarchy from project config: {len(hierarchy_list)} entries "
            "(list format, preserves duplicates)"
        )
        return hierarchy_list

    # Path 1: per-job Excel upload (base64-encoded) — checked second because
    # SubmitTaxonomyJob already sets custom_hierarchy_list=None when b64 is present,
    # so if we reach here with b64, it means per-job upload was the intended source.
    if not status.get("custom_hierarchy_b64"):
        return None
    try:
        cust_bytes = base64.b64decode(status["custom_hierarchy_b64"])

        # 1. Read without assuming header position
        df_raw = pd.read_excel(io.BytesIO(cust_bytes), header=None)

        # 2. Find the row containing N1, N2, N3, N4
        header_row = None
        for idx, row in df_raw.iterrows():
            values = [str(v).strip().upper() for v in row.values]
            if "N1" in values and "N4" in values:
                header_row = idx
                break

        if header_row is None:
            logger.error("Custom hierarchy: headers N1/N4 not found in file")
            return None

        # 3. Re-read with the correct header
        df_hier = pd.read_excel(io.BytesIO(cust_bytes), header=header_row)
        df_hier.columns = [str(c).strip().upper() for c in df_hier.columns]

        if "N4" not in df_hier.columns:
            logger.error(
                f"Custom hierarchy: N4 column missing. Columns: {list(df_hier.columns)}"
            )
            return None

        # 4. Build hierarchy as LIST (preserves duplicate N4s like "Materiais OEM" across brands)
        custom_hierarchy = []
        for _, row in df_hier.iterrows():
            n4 = str(row.get("N4", "")).strip()
            if n4 and n4.upper() != "NAN":
                custom_hierarchy.append(
                    {
                        "N1": str(row.get("N1", "")).strip()
                        if pd.notna(row.get("N1"))
                        else "",
                        "N2": str(row.get("N2", "")).strip()
                        if pd.notna(row.get("N2"))
                        else "",
                        "N3": str(row.get("N3", "")).strip()
                        if pd.notna(row.get("N3"))
                        else "",
                        "N4": n4,
                    }
                )

        logger.info(
            f"Custom hierarchy parsed: {len(custom_hierarchy)} entries "
            "(list format, preserves duplicates)"
        )
        return custom_hierarchy if custom_hierarchy else None
    except Exception as e:
        logger.error(f"Failed to parse custom hierarchy: {e}")
        return None


# ---------------------------------------------------------------------------
# process_single_chunk
# ---------------------------------------------------------------------------


def process_single_chunk(job_info: JobInfoDict, chunk_index: int) -> None:
    """
    Process a single chunk of a job and save the result.
    Does NOT update status.json (caller must call update_job_progress after a parallel batch).
    Passes KB entries and project info to process_dataframe_chunk for few-shot support.
    """
    import pandas as pd
    from src.core_classification import process_dataframe_chunk

    job_dir = job_info["job_dir"]
    status = job_info["status"]
    job_id = job_info["job_id"]
    total_chunks = job_info["total_chunks"]

    chunk_file = os.path.join(job_dir, f"chunk_{chunk_index}.json")
    result_file = os.path.join(job_dir, f"result_{chunk_index}.json")

    logger.info(f"[Worker] job={job_id} chunk={chunk_index}/{total_chunks} — start")

    chunk_start = time.time()
    df_chunk = pd.read_json(chunk_file, orient="records")

    # Use hierarchy already parsed in get_active_jobs (avoids re-decoding base64+Excel per chunk)
    custom_hierarchy = job_info.get("custom_hierarchy")
    hierarchy_lookup = job_info.get("hierarchy_lookup")

    kb_entries = job_info.get("kb_entries", [])
    kb_retriever = job_info.get("kb_retriever")
    project_id = status.get("project_id")
    client_context = status.get("client_context", "")
    sector = status.get("sector", "Padrão")
    desc_col = status.get("desc_column", "Descricao")
    use_web_search = status.get("use_web_search", False)
    models_dir = get_models_dir()

    llm_start = time.time()
    results = process_dataframe_chunk(
        df_chunk,
        desc_column=desc_col,
        sector=sector,
        models_dir=models_dir,
        custom_hierarchy=custom_hierarchy,
        client_context=client_context,
        few_shot_examples=kb_entries if kb_entries else None,
        hierarchy_lookup=hierarchy_lookup,
        use_legacy_ml=(not project_id),  # legacy path only when no project
        project_id=project_id,
        kb_retriever=kb_retriever,
        use_web_search=use_web_search,
    )
    llm_duration = time.time() - llm_start

    with open(result_file, "w") as rf:
        json.dump(results, rf)

    chunk_duration = time.time() - chunk_start
    logger.info(
        f"[Worker] job={job_id} chunk={chunk_index}/{total_chunks} — done "
        f"({len(results)} items, classify={llm_duration:.1f}s, total={chunk_duration:.1f}s)"
    )


# ---------------------------------------------------------------------------
# update_job_progress  (internal helper, kept public for clarity)
# ---------------------------------------------------------------------------


def update_job_progress(job_info: JobInfoDict) -> None:
    """Update processed_chunks count in status.json.

    Uses update_status (atomic read-modify-write) to only update progress
    fields without overwriting the entire status (avoids clobbering CANCELLED).
    """
    job_dir = job_info["job_dir"]
    total_chunks = job_info["total_chunks"]
    processed_so_far = sum(
        1
        for j in range(total_chunks)
        if os.path.exists(os.path.join(job_dir, f"result_{j}.json"))
    )
    job_info["status"]["processed_chunks"] = processed_so_far
    update_status(job_info["status_path"], {"processed_chunks": processed_so_far})


# ---------------------------------------------------------------------------
# consolidate_job
# ---------------------------------------------------------------------------


def consolidate_job(job_info: JobInfoDict) -> None:
    """
    Consolidate results from all chunks into a final Excel file and mark as CLASSIFIED.
    Status is set to "CLASSIFIED" (not "COMPLETED") because human review must happen first.
    """
    import pandas as pd
    from src.taxonomy_engine import generate_analytics, generate_summary

    job_dir = job_info["job_dir"]
    status = job_info["status"]
    job_id = job_info["job_id"]
    total_chunks = job_info["total_chunks"]
    status_path = job_info["status_path"]

    consolidate_start = time.time()
    logger.info(f"[Worker] job={job_id} — consolidating {total_chunks} chunks")

    # Accumulate classification results
    results_accumulated = []
    for i in range(total_chunks):
        res_path = os.path.join(job_dir, f"result_{i}.json")
        if os.path.exists(res_path):
            with open(res_path, "r") as rf:
                results_accumulated.extend(json.load(rf))

    results_df = pd.DataFrame(results_accumulated)

    # Join with original data (descriptions + other columns)
    original_chunks = []
    for i in range(total_chunks):
        chunk_path = os.path.join(job_dir, f"chunk_{i}.json")
        if os.path.exists(chunk_path):
            with open(chunk_path, "r") as cf:
                original_chunks.extend(json.load(cf))

    if original_chunks and len(original_chunks) == len(results_accumulated):
        original_df = pd.DataFrame(original_chunks)
        # Drop internal/temporary columns
        cols_to_drop = [c for c in original_df.columns if c.startswith("_")]
        original_df.drop(columns=cols_to_drop, errors="ignore", inplace=True)
        # Remove classification columns from original to avoid duplicate labels
        overlap = [c for c in original_df.columns if c in results_df.columns]
        if overlap:
            logger.info(
                f"[Consolidate] Dropping overlapping columns from original: {overlap}"
            )
            original_df.drop(columns=overlap, inplace=True)
        final_df = pd.concat(
            [original_df.reset_index(drop=True), results_df.reset_index(drop=True)],
            axis=1,
        )
    else:
        final_df = results_df

    # Fill blank/nan cells with "Não Identificado"
    _nan_strings = [
        v
        for v in INCOMPLETE_VALUES
        if v not in ("", "Não Identificado", "Nao Identificado")
    ]
    for col in ["N1", "N2", "N3", "N4"]:
        if col in final_df.columns:
            final_df[col] = (
                final_df[col]
                .fillna("Não Identificado")
                .replace("", "Não Identificado")
                .replace(_nan_strings, "Não Identificado")
            )
    if "status" in final_df.columns:
        final_df["status"] = final_df["status"].fillna("Nenhum").replace("", "Nenhum")

    # Zero confidence for incomplete classifications (any N-level is "Não Identificado")
    if "confidence" in final_df.columns:
        incomplete_mask = False
        for col in ["N1", "N2", "N3", "N4"]:
            if col in final_df.columns:
                incomplete_mask = incomplete_mask | (
                    final_df[col] == "Não Identificado"
                )
        final_df.loc[incomplete_mask, "confidence"] = 0.0

    # Remove legacy columns not relevant for LLM-direct path (before analytics/Excel)
    for col in ["status", "matched_terms"]:
        if col in final_df.columns:
            final_df.drop(columns=[col], inplace=True)

    # Map source to friendly labels
    if "source" in final_df.columns:
        final_df["source"] = final_df["source"].map(friendly_source_label)

    # Analytics and Summary (derive classified/unclassified from N1-N4)
    analytics = generate_analytics(final_df)
    summary = generate_summary(final_df, status.get("desc_column", "Descricao"))

    # Generate Excel — salvar em arquivo separado (não no result.json)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        final_df.to_excel(writer, index=False, sheet_name="Classificação")
    output.seek(0)
    xlsx_b64 = base64.b64encode(output.getvalue()).decode("utf-8")
    del output  # liberar BytesIO imediatamente

    # Salvar Excel b64 em arquivo separado (reduz result.json em ~10-15 MB)
    excel_b64_path = os.path.join(job_dir, "classified_excel_b64.txt")
    with open(excel_b64_path, "w", encoding="utf-8") as ef:
        ef.write(xlsx_b64)
    del xlsx_b64  # liberar string b64

    # Gerar result.json SEM fileContent
    final_result = {
        "items": final_df.to_dict(orient="records"),
        "analytics": analytics,
        "summary": summary,
        "filename": f"classified_{status['filename']}",
    }

    del final_df  # liberar DataFrame antes de serializar

    with open(os.path.join(job_dir, "result.json"), "w") as f:
        f.write(safe_json_dumps(final_result))

    # Calculate fallback percentage (items with confidence 0.0)
    total_items = len(results_accumulated)
    fallback_count = sum(
        1 for r in results_accumulated if float(r.get("confidence", 0)) == 0.0
    )
    fallback_pct = (
        round(fallback_count / total_items * 100, 1) if total_items > 0 else 0.0
    )

    # Set status to CLASSIFIED (not COMPLETED - review must happen first)
    # Use locked_status to check if job was CANCELLED concurrently
    with locked_status(status_path) as current:
        if current.get("status") in ("CANCELLED", "ERROR", "CLASSIFIED", "COMPLETED"):
            logger.info(
                f"[Worker] job={job_id} has status '{current.get('status')}', skipping consolidation"
            )
            return
        current["status"] = "CLASSIFIED"
        current["download_filename"] = final_result.get("filename", "")
        current["fallback_pct"] = fallback_pct
        if fallback_pct > 50.0:
            current["warning"] = (
                f"{fallback_pct}% dos itens não foram classificados — "
                "a API pode estar instável. Considere re-submeter o job."
            )
            logger.warning(
                f"[Worker] job={job_id} — CLASSIFIED com {fallback_pct}% fallback"
            )

    # Clean up intermediate chunk and result files
    for chunk_file in glob_mod.glob(os.path.join(job_dir, "chunk_*.json")):
        try:
            os.remove(chunk_file)
        except OSError:
            pass
    for res_chunk in glob_mod.glob(os.path.join(job_dir, "result_*.json")):
        try:
            os.remove(res_chunk)
        except OSError:
            pass

    consolidate_duration = time.time() - consolidate_start
    logger.info(
        f"[Worker] job={job_id} — CLASSIFIED "
        f"({len(results_accumulated)} items, consolidate={consolidate_duration:.1f}s)"
    )


# ---------------------------------------------------------------------------
# process_single_job  (queue-triggered — processes ONE job to CLASSIFIED)
# ---------------------------------------------------------------------------


def process_single_job(job_id: str) -> None:
    """Process a single job from PENDING to CLASSIFIED (queue trigger path).

    Unlike run_worker_cycle(), this function:
    - Receives job_id directly (no directory scan)
    - Processes 1 job completely (no round-robin)
    - No time budget — queue visibility timeout (30min Flex Consumption) controls this
    - Re-raises exceptions so the queue runtime can retry via dequeue count
    """
    import traceback

    jobs_root = get_jobs_dir()
    job_dir = os.path.join(jobs_root, job_id)
    status_path = os.path.join(job_dir, "status.json")

    if not os.path.isdir(job_dir) or not os.path.exists(status_path):
        logger.warning(f"[Worker] Job {job_id} not found — skipping")
        return

    # Guard check: skip non-actionable jobs (fast path, no lock needed)
    status = read_status(status_path)
    current = status.get("status", "")
    if current not in ("PENDING", "PROCESSING"):
        logger.info(f"[Worker] Job {job_id} has status '{current}' — skipping")
        return

    # Atomic check-and-set: re-verify + mutate under lock
    # Uses processing_worker_id as a simple lease to prevent duplicate processing
    import uuid as uuid_mod

    worker_id = str(uuid_mod.uuid4())
    with locked_status(status_path) as data:
        current = data.get("status", "")
        if current not in ("PENDING", "PROCESSING"):
            logger.info(
                f"[Worker] Job {job_id} status changed to '{current}' — skipping"
            )
            return
        if current == "PROCESSING" and data.get("processing_worker_id"):
            logger.info(
                f"[Worker] Job {job_id} already being processed by "
                f"{data.get('processing_worker_id')} — skipping"
            )
            return
        data["status"] = "PROCESSING"
        data["processing_worker_id"] = worker_id
    # Re-read after atomic transition
    status = read_status(status_path)

    logger.info(
        f"[Worker] Processing job {job_id} ({status.get('total_chunks')} chunks)"
    )

    try:
        # Setup: hierarchy, KB, KBRetriever
        job_info = _prepare_job_info(job_id, job_dir, status_path, status)

        # Process chunks in parallel batches
        while True:
            # Check for cancellation/completion between batches
            current_status = read_status(status_path)
            if current_status.get("status") in (
                "CANCELLED",
                "CLASSIFIED",
                "COMPLETED",
                "ERROR",
            ):
                logger.info(
                    f"[Worker] Job {job_id} status='{current_status.get('status')}' — stopping"
                )
                return

            chunks = find_next_chunks(job_info, max_count=MAX_PARALLEL_CHUNKS)
            if not chunks:
                break

            logger.info(
                f"[Worker] job={job_id} processing {len(chunks)} chunk(s): {chunks}"
            )

            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CHUNKS) as executor:
                futures = {
                    executor.submit(process_single_chunk, job_info, idx): idx
                    for idx in chunks
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    future.result()  # re-raises on error
                    update_job_progress(job_info)

        # All chunks done — consolidate
        consolidate_job(job_info)

    except Exception as e:
        logger.error(
            f"[Worker] Error processing job {job_id}: {e}\n{traceback.format_exc()}"
        )
        # Don't write ERROR here — the job stays PROCESSING so queue retries
        # (maxDequeueCount=5) can re-enter and process remaining chunks.
        # After all retries are exhausted, the message goes to poison queue,
        # and the hourly cleanup timer marks PROCESSING > 1h as ERROR.
        raise  # re-raise so queue runtime retries


def cleanup_old_jobs(jobs_root: str, max_age_days: int = 30) -> int:
    """Delete job directories for COMPLETED/ERROR/CANCELLED jobs older than max_age_days.

    Only deletes terminal-state jobs. Returns count of deleted job directories.
    """
    import shutil

    deleted = 0
    _DELETABLE_STATUSES = ("COMPLETED", "ERROR", "CANCELLED")

    for job_id in os.listdir(jobs_root):
        job_dir = os.path.join(jobs_root, job_id)
        status_path = os.path.join(job_dir, "status.json")
        if not os.path.isdir(job_dir) or not os.path.exists(status_path):
            continue
        try:
            status = read_status(status_path)
            if status.get("status") not in _DELETABLE_STATUSES:
                continue
            created_at = status.get("created_at")
            if not created_at:
                continue
            created_dt = datetime.fromisoformat(created_at)
            age_days = (datetime.now(timezone.utc) - created_dt).total_seconds() / 86400
            if age_days > max_age_days:
                shutil.rmtree(job_dir, ignore_errors=True)
                deleted += 1
                logger.info(
                    f"[Retention] Deleted job {job_id} "
                    f"(status={status.get('status')}, age={age_days:.0f} days)"
                )
        except Exception as e:
            logger.error(f"[Retention] Error checking job {job_id}: {e}")

    return deleted
