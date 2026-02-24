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
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils import get_jobs_dir, get_models_dir, friendly_source_label
from src.project_manager import get_project, resolve_hierarchy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALE_THRESHOLD_SECONDS = 3600   # 1 hour - jobs PROCESSING beyond this become ERROR
MAX_PARALLEL_CHUNKS = 5           # Max simultaneous chunks across all active jobs
MAX_PROCESSING_TIME = 20 * 60    # 20-minute budget per worker cycle


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
            with open(status_path, "r") as f:
                status = json.load(f)
            if status.get("status") != "PROCESSING":
                continue
            created_at = status.get("created_at")
            if not created_at:
                continue
            created_dt = datetime.fromisoformat(created_at)
            elapsed = (datetime.utcnow() - created_dt).total_seconds()
            if elapsed > STALE_THRESHOLD_SECONDS:
                logger.warning(
                    f"[Worker] Job {job_id} stuck for {elapsed/60:.0f}min. Marking as ERROR."
                )
                status["status"] = "ERROR"
                status["error"] = f"Job expired after {elapsed/60:.0f} minutes without completing"
                with open(status_path, "w") as f:
                    json.dump(status, f)
        except Exception as e:
            logger.error(f"[Worker] Error checking stale job {job_id}: {e}")


# ---------------------------------------------------------------------------
# get_active_jobs
# ---------------------------------------------------------------------------

def get_active_jobs(jobs_root: str) -> list:
    """
    Collect active jobs (PENDING/PROCESSING), transition PENDING -> PROCESSING,
    parse custom_hierarchy ONCE per job, and load the project KB for few-shot retrieval.
    """
    models_dir = get_models_dir()
    active = []

    for job_id in os.listdir(jobs_root):
        job_dir = os.path.join(jobs_root, job_id)
        status_path = os.path.join(job_dir, "status.json")
        if not os.path.isdir(job_dir) or not os.path.exists(status_path):
            continue
        try:
            with open(status_path, "r") as f:
                status = json.load(f)

            if status.get("status") in ["COMPLETED", "CLASSIFIED", "ERROR", "CANCELLED"]:
                continue

            if status["status"] == "PENDING":
                status["status"] = "PROCESSING"
                with open(status_path, "w") as f:
                    json.dump(status, f)

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
                    use_sector_kb = project_config.get("use_sector_kb", True) if project_config else True
                    if sector_slug and use_sector_kb:
                        try:
                            sector_kb = KnowledgeBase(sector_slug, models_dir, entity_type="sector")
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

            active.append({
                "job_id": job_id,
                "job_dir": job_dir,
                "status_path": status_path,
                "status": status,
                "total_chunks": status["total_chunks"],
                "custom_hierarchy": custom_hierarchy,
                "hierarchy_lookup": hierarchy_lookup,
                "kb_entries": kb_entries,
                "kb_retriever": kb_retriever,
            })
        except Exception as e:
            logger.error(f"[Worker] Error reading job {job_id}: {e}")

    return active


# ---------------------------------------------------------------------------
# find_next_chunks
# ---------------------------------------------------------------------------

def find_next_chunks(job_info: dict, max_count: int = 1, exclude: set = None) -> list:
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

def parse_custom_hierarchy(status: dict):
    """
    Decode custom_hierarchy_b64 from job status, if present.
    Robust: detects the header row (N1,N2,N3,N4) even if there are blank rows above it.
    Returns a list of dicts (preserves duplicate N4 names across different N3 branches).
    """
    import pandas as pd

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
            if 'N1' in values and 'N4' in values:
                header_row = idx
                break

        if header_row is None:
            logger.error("Custom hierarchy: headers N1/N4 not found in file")
            return None

        # 3. Re-read with the correct header
        df_hier = pd.read_excel(io.BytesIO(cust_bytes), header=header_row)
        df_hier.columns = [str(c).strip().upper() for c in df_hier.columns]

        if 'N4' not in df_hier.columns:
            logger.error(f"Custom hierarchy: N4 column missing. Columns: {list(df_hier.columns)}")
            return None

        # 4. Build hierarchy as LIST (preserves duplicate N4s like "Materiais OEM" across brands)
        custom_hierarchy = []
        for _, row in df_hier.iterrows():
            n4 = str(row.get('N4', '')).strip()
            if n4 and n4.upper() != 'NAN':
                custom_hierarchy.append({
                    'N1': str(row.get('N1', '')).strip() if pd.notna(row.get('N1')) else '',
                    'N2': str(row.get('N2', '')).strip() if pd.notna(row.get('N2')) else '',
                    'N3': str(row.get('N3', '')).strip() if pd.notna(row.get('N3')) else '',
                    'N4': n4,
                })

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

def process_single_chunk(job_info: dict, chunk_index: int) -> None:
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

    logger.info(f"[Worker] Processing Job {job_id} - Chunk {chunk_index}/{total_chunks}")

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
    models_dir = get_models_dir()

    results = process_dataframe_chunk(
        df_chunk,
        desc_column=desc_col,
        sector=sector,
        models_dir=models_dir,
        custom_hierarchy=custom_hierarchy,
        client_context=client_context,
        few_shot_examples=kb_entries if kb_entries else None,
        hierarchy_lookup=hierarchy_lookup,
        use_legacy_ml=(not project_id),   # legacy path only when no project
        project_id=project_id,
        kb_retriever=kb_retriever,
    )

    with open(result_file, "w") as rf:
        json.dump(results, rf)


# ---------------------------------------------------------------------------
# update_job_progress  (internal helper, kept public for clarity)
# ---------------------------------------------------------------------------

def update_job_progress(job_info: dict) -> None:
    """Update processed_chunks count in status.json.

    Called from the main thread after each chunk completes (via as_completed loop).
    Safe because the loop is sequential — no concurrent writes to status.json.
    """
    job_dir = job_info["job_dir"]
    total_chunks = job_info["total_chunks"]
    processed_so_far = sum(
        1 for j in range(total_chunks)
        if os.path.exists(os.path.join(job_dir, f"result_{j}.json"))
    )
    job_info["status"]["processed_chunks"] = processed_so_far
    with open(job_info["status_path"], "w") as f:
        json.dump(job_info["status"], f)


# ---------------------------------------------------------------------------
# consolidate_job
# ---------------------------------------------------------------------------

def consolidate_job(job_info: dict) -> None:
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

    logger.info(f"[Worker] Job {job_id} completed all chunks. Consolidating...")

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
        cols_to_drop = [c for c in original_df.columns if c.startswith('_')]
        original_df.drop(columns=cols_to_drop, errors='ignore', inplace=True)
        # Remove classification columns from original to avoid duplicate labels
        overlap = [c for c in original_df.columns if c in results_df.columns]
        if overlap:
            logger.info(f"[Consolidate] Dropping overlapping columns from original: {overlap}")
            original_df.drop(columns=overlap, inplace=True)
        final_df = pd.concat(
            [original_df.reset_index(drop=True), results_df.reset_index(drop=True)],
            axis=1
        )
    else:
        final_df = results_df

    # Fill blank cells with "Não Identificado"
    for col in ["N1", "N2", "N3", "N4"]:
        if col in final_df.columns:
            final_df[col] = final_df[col].fillna("Não Identificado").replace("", "Não Identificado")
    if "status" in final_df.columns:
        final_df["status"] = final_df["status"].fillna("Nenhum").replace("", "Nenhum")

    # Zero confidence for incomplete classifications (any N-level is "Não Identificado")
    if "confidence" in final_df.columns:
        incomplete_mask = False
        for col in ["N1", "N2", "N3", "N4"]:
            if col in final_df.columns:
                incomplete_mask = incomplete_mask | (final_df[col] == "Não Identificado")
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

    # Generate Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_df.to_excel(writer, index=False, sheet_name='Classificação')
    output.seek(0)
    xlsx_b64 = base64.b64encode(output.getvalue()).decode("utf-8")

    final_result = {
        "items": final_df.to_dict(orient="records"),
        "analytics": analytics,
        "summary": summary,
        "fileContent": xlsx_b64,
        "filename": f"classified_{status['filename']}"
    }

    with open(os.path.join(job_dir, "result.json"), "w") as f:
        json.dump(final_result, f)

    # Set status to CLASSIFIED (not COMPLETED - review must happen first)
    status_data = status
    status_data["status"] = "CLASSIFIED"  # Was: "COMPLETED"
    with open(status_path, "w") as f:
        json.dump(status_data, f)

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

    logger.info(f"[Worker] Job {job_id} consolidated and marked as CLASSIFIED.")


# ---------------------------------------------------------------------------
# run_worker_cycle  (orchestrator — mirrors ProcessTaxonomyWorker from v2)
# ---------------------------------------------------------------------------

def run_worker_cycle() -> None:
    """
    Main worker loop: round-robin parallel processing of chunks across active jobs.
    Mirrors the logic of ProcessTaxonomyWorker from v2/function_app.py.
    Call this from an Azure Timer Trigger or from run_local_worker.py.
    """
    jobs_root = get_jobs_dir()
    if not os.path.exists(jobs_root):
        logger.info(f"[Worker] No jobs directory at {jobs_root}")
        return

    # 1. Auto-cleanup stale jobs (PROCESSING > 1h -> ERROR)
    cleanup_stale_jobs(jobs_root)

    # 2. Collect active jobs (PENDING -> PROCESSING)
    active_jobs = get_active_jobs(jobs_root)
    if not active_jobs:
        return

    logger.info(
        f"[Worker] {len(active_jobs)} active job(s): {[j['job_id'][:8] for j in active_jobs]}"
    )

    # 3. Round-robin parallel: up to MAX_PARALLEL_CHUNKS simultaneous chunks across all jobs
    worker_start_time = time.time()

    while True:
        elapsed = time.time() - worker_start_time
        if elapsed > MAX_PROCESSING_TIME:
            logger.info(
                f"[Worker] Time budget reached ({elapsed:.0f}s). "
                "Jobs will continue in the next cycle."
            )
            break

        # Collect up to MAX_PARALLEL_CHUNKS via fair round-robin across jobs
        batch = []
        pending = [j for j in active_jobs if j["status"].get("status") not in ("ERROR", "CANCELLED")]
        assigned = {j["job_id"]: set() for j in pending}

        # Round-robin: 1 chunk per job per round, repeat until batch is full
        while len(batch) < MAX_PARALLEL_CHUNKS and pending:
            next_round = []
            for job in pending:
                if len(batch) >= MAX_PARALLEL_CHUNKS:
                    break
                jid = job["job_id"]
                available = find_next_chunks(job, max_count=1, exclude=assigned[jid])
                if available:
                    batch.append((job, available[0]))
                    assigned[jid].add(available[0])
                    next_round.append(job)
            pending = next_round

        if not batch:
            break

        logger.info(
            f"[Worker] Processing {len(batch)} chunk(s) in parallel: "
            f"{[(j['job_id'][:8], c) for j, c in batch]}"
        )

        # Process batch in parallel
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CHUNKS) as executor:
            futures = {
                executor.submit(process_single_chunk, job, idx): (job, idx)
                for job, idx in batch
            }
            for future in as_completed(futures):
                job, idx = futures[future]
                try:
                    future.result()
                    # Update progress immediately after each chunk completes
                    if job["status"].get("status") != "ERROR":
                        update_job_progress(job)
                except Exception as e:
                    logger.error(f"[Worker] Error in Job {job['job_id']} chunk {idx}: {e}")
                    job["status"]["status"] = "ERROR"
                    job["status"]["error"] = str(e)
                    with open(job["status_path"], "w") as f:
                        json.dump(job["status"], f)

    # 4. Consolidate jobs that have completed all chunks
    for job_info in active_jobs:
        if job_info["status"].get("status") in ("ERROR", "CANCELLED"):
            continue
        all_done = all(
            os.path.exists(os.path.join(job_info["job_dir"], f"result_{i}.json"))
            for i in range(job_info["total_chunks"])
        )
        if all_done:
            try:
                consolidate_job(job_info)
            except Exception as e:
                import traceback
                logger.error(
                    f"[Worker] Error consolidating Job {job_info['job_id']}: "
                    f"{e}\n{traceback.format_exc()}"
                )
                job_info["status"]["status"] = "ERROR"
                job_info["status"]["error"] = f"Consolidation error: {e}"
                with open(job_info["status_path"], "w") as f:
                    json.dump(job_info["status"], f)
