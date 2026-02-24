"""Blueprint for taxonomy classification endpoints."""
import os
import json
import io
import base64
import logging
import math
import uuid
from datetime import datetime

import azure.functions as func
from src.utils import get_models_dir, get_jobs_dir, safe_json_dumps

logger = logging.getLogger(__name__)
classification_bp = func.Blueprint()

CHUNK_SIZE = 500


def _parse_custom_hierarchy_b64(custom_hierarchy_b64: str):
    """Decode a base64-encoded Excel file containing a custom hierarchy (N1,N2,N3,N4).
    Returns a list of dicts or None on failure.
    Detects the header row automatically (looks for N1 and N4 in any row).
    """
    import pandas as pd

    if not custom_hierarchy_b64:
        return None
    try:
        cust_bytes = base64.b64decode(custom_hierarchy_b64)

        # Read without assuming header position
        df_raw = pd.read_excel(io.BytesIO(cust_bytes), header=None)

        # Find the row containing N1 and N4 headers
        header_row = None
        for idx, row in df_raw.iterrows():
            values = [str(v).strip().upper() for v in row.values]
            if "N1" in values and "N4" in values:
                header_row = idx
                break

        if header_row is None:
            logger.error("Custom hierarchy: headers N1/N4 not found in file")
            return None

        # Re-read with correct header row
        df_hier = pd.read_excel(io.BytesIO(cust_bytes), header=header_row)
        df_hier.columns = [str(c).strip().upper() for c in df_hier.columns]

        if "N4" not in df_hier.columns:
            logger.error(f"Custom hierarchy: N4 column missing. Columns: {list(df_hier.columns)}")
            return None

        # Build list (preserves duplicate N4 values across different N1/N2/N3 branches)
        custom_hierarchy = []
        for _, row in df_hier.iterrows():
            import pandas as pd_inner
            n4 = str(row.get("N4", "")).strip()
            if n4 and n4.upper() != "NAN":
                custom_hierarchy.append({
                    "N1": str(row.get("N1", "")).strip() if pd_inner.notna(row.get("N1")) else "",
                    "N2": str(row.get("N2", "")).strip() if pd_inner.notna(row.get("N2")) else "",
                    "N3": str(row.get("N3", "")).strip() if pd_inner.notna(row.get("N3")) else "",
                    "N4": n4,
                })

        logger.info(f"Custom hierarchy parsed: {len(custom_hierarchy)} entries (list, preserves duplicates)")
        return custom_hierarchy if custom_hierarchy else None
    except Exception as e:
        logger.error(f"Failed to parse custom hierarchy: {e}")
        return None


@classification_bp.route(route="SubmitTaxonomyJob", methods=["POST", "OPTIONS"],
                          auth_level=func.AuthLevel.ANONYMOUS)
def SubmitTaxonomyJob(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/SubmitTaxonomyJob
    Accepts a file upload, splits it into chunks, and queues it for async processing.
    Supports both legacy (sector) and project-based (projectId) paths.

    Body:
        fileContent (str): Base64-encoded Excel or CSV file.
        sector (str): Sector name (legacy path, used if projectId is not provided).
        projectId (str, optional): Project ID (new path). If provided, loads project config,
            resolves the hierarchy, and uses the project's sector.
        originalFilename (str, optional): Original file name.
        clientContext (str, optional): Free-text context for LLM prompts (overridden by project
            config when projectId is provided).
        customHierarchy (str, optional): Base64-encoded Excel with custom hierarchy (legacy path,
            ignored when projectId is provided and the project has its own hierarchy).
        dictionaryContent (str, optional): Base64-encoded custom dictionary file.

    Returns 202 Accepted with {jobId, status, total_chunks}.
    """
    import pandas as pd

    # Handle CORS preflight
    if req.method == "OPTIONS":
        return func.HttpResponse(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )

    logger.info("SubmitTaxonomyJob HTTP trigger processed a request.")

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON body", status_code=400)

    file_content_b64 = req_body.get("fileContent")
    if not file_content_b64:
        return func.HttpResponse("Missing fileContent", status_code=400)

    models_dir = get_models_dir()
    jobs_dir = get_jobs_dir()

    # --- Resolve sector and project context ---
    project_id = req_body.get("projectId", "").strip()
    client_context = req_body.get("clientContext", "")
    custom_hierarchy_b64 = req_body.get("customHierarchy")  # legacy path
    project_config = None

    if project_id:
        # New path: load project config, resolve hierarchy
        try:
            from src.project_manager import get_project, resolve_hierarchy
            project_config = get_project(project_id, models_dir)
            if project_config is None:
                return func.HttpResponse(
                    json.dumps({"error": f"Project '{project_id}' not found"}),
                    status_code=404, mimetype="application/json"
                )
            sector = project_config.get("sector", "padrao").strip().capitalize()
            # Project client_context takes precedence over body clientContext
            client_context = project_config.get("client_context", "") or client_context

            # Resolve hierarchy: per-job upload always overrides project hierarchy
            resolved_hierarchy, hierarchy_source = resolve_hierarchy(project_id, models_dir)
            if custom_hierarchy_b64:
                # Per-job hierarchy uploaded: use it, ignore project's
                custom_hierarchy_list = None
            else:
                # No per-job upload: fall back to project hierarchy (may be None for padrao)
                custom_hierarchy_list = resolved_hierarchy
                custom_hierarchy_b64 = None
        except Exception as e:
            logger.error(f"SubmitTaxonomyJob: failed to load project '{project_id}': {e}")
            return func.HttpResponse(
                json.dumps({"error": f"Failed to load project: {e}"}),
                status_code=500, mimetype="application/json"
            )
    else:
        # Legacy path: sector from body
        sector_raw = req_body.get("sector")
        if not sector_raw:
            return func.HttpResponse("Missing projectId or sector", status_code=400)
        sector = sector_raw.strip().capitalize()
        custom_hierarchy_list = None  # will be parsed by worker from b64

    # --- Create job directory ---
    session_id = str(uuid.uuid4())
    job_dir = os.path.join(jobs_dir, session_id)
    os.makedirs(job_dir, exist_ok=True)
    logger.info(f"[Submit] Job {session_id} created at {job_dir}")

    try:
        # --- Decode and load file ---
        file_bytes = base64.b64decode(file_content_b64)
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=";", encoding="utf-8", on_bad_lines="skip")
            except Exception:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=",", encoding="utf-8", on_bad_lines="skip")

        # Identify description column (second non-unnamed column heuristic, same as v2)
        valid_cols = [c for c in df.columns if not str(c).startswith("Unnamed")]
        if len(valid_cols) < 2:
            return func.HttpResponse("Invalid file columns.", status_code=400)
        desc_col = valid_cols[1]

        # Sort by description to group similar items in the same LLM batch
        df = df.sort_values(
            by=desc_col,
            key=lambda s: s.str.lower().fillna(""),
            na_position="last"
        ).reset_index(drop=True)

        # --- Chunking ---
        num_chunks = math.ceil(len(df) / CHUNK_SIZE)

        # Build metadata / status
        metadata = {
            "job_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "status": "PENDING",
            "sector": sector,
            "filename": req_body.get("originalFilename", "upload.xlsx"),
            "desc_column": desc_col,
            "total_rows": len(df),
            "total_chunks": num_chunks,
            "processed_chunks": 0,
            "client_context": client_context,
            "dictionary_content_b64": req_body.get("dictionaryContent"),
            # Project-based fields
            "project_id": project_id or None,
        }

        # Hierarchy storage: prefer list (project path) over b64 (legacy path)
        if custom_hierarchy_list is not None:
            metadata["custom_hierarchy_list"] = custom_hierarchy_list
            metadata["custom_hierarchy_b64"] = None
        else:
            metadata["custom_hierarchy_list"] = None
            metadata["custom_hierarchy_b64"] = custom_hierarchy_b64

        # --- Save chunks ---
        for i in range(num_chunks):
            chunk_df = df.iloc[i * CHUNK_SIZE: (i + 1) * CHUNK_SIZE]
            chunk_path = os.path.join(job_dir, f"chunk_{i}.json")
            chunk_df.to_json(chunk_path, orient="records")

        # --- Save status file ---
        with open(os.path.join(job_dir, "status.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False)

        return func.HttpResponse(
            body=safe_json_dumps({"jobId": session_id, "status": "PENDING", "total_chunks": num_chunks}),
            status_code=202,
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )

    except Exception as e:
        logger.error(f"SubmitTaxonomyJob error: {e}", exc_info=True)
        return func.HttpResponse(f"Internal Error: {str(e)}", status_code=500)


@classification_bp.route(route="GetTaxonomyJobStatus", methods=["GET", "OPTIONS"],
                          auth_level=func.AuthLevel.ANONYMOUS)
def GetTaxonomyJobStatus(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetTaxonomyJobStatus?jobId=xxx
    Polls the status of a specific job.
    Returns: status (PENDING/PROCESSING/COMPLETED/ERROR), progress %, and result if done.
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=200, headers={"Access-Control-Allow-Origin": "*"})

    job_id = req.params.get("jobId")
    if not job_id:
        return func.HttpResponse("Missing jobId", status_code=400)

    jobs_dir = get_jobs_dir()
    job_dir = os.path.join(jobs_dir, job_id)
    status_file = os.path.join(job_dir, "status.json")

    if not os.path.exists(status_file):
        return func.HttpResponse("Job not found", status_code=404)

    try:
        with open(status_file, "r", encoding="utf-8") as f:
            status = json.load(f)

        # Calculate progress
        total = status.get("total_chunks", 1)
        processed = status.get("processed_chunks", 0)
        pct = min(int((processed / total) * 100), 99) if status["status"] != "COMPLETED" else 100

        if status["status"] == "PROCESSING":
            total_rows = status.get("total_rows", total * CHUNK_SIZE)
            items_done = min(processed * CHUNK_SIZE, total_rows)
            message = f"{items_done:,} de {total_rows:,} itens processados"
        elif status["status"] == "PENDING":
            message = "Aguardando inicio do processamento..."
        else:
            message = status["status"]

        response = {
            "jobId": job_id,
            "status": status["status"],
            "progress_pct": pct,
            "message": message,
        }

        if status["status"] == "COMPLETED":
            result_file = os.path.join(job_dir, "result.json")
            if os.path.exists(result_file):
                with open(result_file, "r", encoding="utf-8") as rf:
                    response.update(json.load(rf))
            else:
                response["status"] = "ERROR"
                response["message"] = "Result file missing."

        return func.HttpResponse(
            body=safe_json_dumps(response),
            status_code=200,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    except Exception as e:
        logger.error(f"GetTaxonomyJobStatus error: {e}", exc_info=True)
        return func.HttpResponse(f"Error reading status: {e}", status_code=500)


@classification_bp.route(route="CancelJob", methods=["POST", "OPTIONS"],
                          auth_level=func.AuthLevel.ANONYMOUS)
def CancelJob(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/CancelJob?jobId=xxx
    Cancels a PENDING or PROCESSING job by writing CANCELLED to status.json.
    Returns 200 with {jobId, status: "CANCELLED"}.
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
        )

    job_id = req.params.get("jobId")
    if not job_id:
        return func.HttpResponse("Missing jobId", status_code=400)

    jobs_dir = get_jobs_dir()
    job_dir = os.path.join(jobs_dir, job_id)
    status_file = os.path.join(job_dir, "status.json")

    if not os.path.exists(status_file):
        return func.HttpResponse("Job not found", status_code=404)

    try:
        with open(status_file, "r", encoding="utf-8") as f:
            status = json.load(f)

        current_status = status.get("status", "")
        if current_status not in ("PENDING", "PROCESSING"):
            return func.HttpResponse(
                body=safe_json_dumps({
                    "error": f"Cannot cancel job with status '{current_status}'. Only PENDING or PROCESSING jobs can be cancelled."
                }),
                status_code=409,
                mimetype="application/json",
                headers={"Access-Control-Allow-Origin": "*"},
            )

        status["status"] = "CANCELLED"
        status["cancelled_at"] = datetime.utcnow().isoformat()

        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False)

        logger.info(f"[CancelJob] Job {job_id} cancelled (was {current_status})")

        return func.HttpResponse(
            body=safe_json_dumps({"jobId": job_id, "status": "CANCELLED"}),
            status_code=200,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    except Exception as e:
        logger.error(f"CancelJob error: {e}", exc_info=True)
        return func.HttpResponse(f"Error cancelling job: {e}", status_code=500)


@classification_bp.route(route="GetJobResults", methods=["GET", "OPTIONS"],
                          auth_level=func.AuthLevel.ANONYMOUS)
def GetJobResults(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetJobResults?jobId=xxx
    Returns classified items as a flat JSON array for human review.
    Merges all result_X.json files from the job directory.

    Returns: {jobId, status, items: [{index, description, N1, N2, N3, N4,
              confidence, source, status}], total}
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=200, headers={"Access-Control-Allow-Origin": "*"})

    job_id = req.params.get("jobId", "").strip()
    if not job_id:
        return func.HttpResponse("Missing jobId", status_code=400)

    jobs_dir = get_jobs_dir()
    job_dir = os.path.join(jobs_dir, job_id)
    status_file = os.path.join(job_dir, "status.json")

    if not os.path.isdir(job_dir) or not os.path.exists(status_file):
        return func.HttpResponse("Job not found", status_code=404)

    try:
        with open(status_file, "r", encoding="utf-8") as f:
            status_data = json.load(f)

        job_status = status_data.get("status", "UNKNOWN")
        total_chunks = status_data.get("total_chunks", 0)
        desc_col = status_data.get("desc_column", "Descricao")

        # Load result.json once — needed for analytics/summary and as authoritative source
        analytics = None
        summary = None
        result_file = os.path.join(job_dir, "result.json")
        result_json = None
        if os.path.exists(result_file):
            with open(result_file, "r", encoding="utf-8") as rf:
                result_json = json.load(rf)
            analytics = result_json.get("analytics")
            summary = result_json.get("summary")

        items = []

        # For CLASSIFIED/COMPLETED jobs, always use result.json (authoritative).
        # Reading individual result_X.json is unsafe due to race condition:
        # consolidate_job deletes them AFTER writing CLASSIFIED, so a concurrent
        # GetJobResults call may find only a subset, producing truncated results.
        if job_status in ("CLASSIFIED", "COMPLETED") and result_json:
            raw_items = result_json.get("items", [])
            for idx, row in enumerate(raw_items):
                items.append({
                    "index": idx,
                    "description": row.get(desc_col, row.get("description", "")),
                    "N1": row.get("N1", "Nao Identificado"),
                    "N2": row.get("N2", "Nao Identificado"),
                    "N3": row.get("N3", "Nao Identificado"),
                    "N4": row.get("N4", "Nao Identificado"),
                    "confidence": row.get("confidence", 0.0),
                    "source": row.get("source", ""),
                    "status": row.get("status", "") or (
                        "Nenhum" if any(
                            str(row.get(lvl, "")).strip() in ("", "Não Identificado", "Nao Identificado")
                            for lvl in ("N1", "N2", "N3", "N4")
                        ) else "Unico"
                    ),
                })
        else:
            # In-progress jobs (PROCESSING): read individual result_X.json chunks
            global_index = 0
            for i in range(total_chunks):
                result_path = os.path.join(job_dir, f"result_{i}.json")
                chunk_path = os.path.join(job_dir, f"chunk_{i}.json")

                if not os.path.exists(result_path):
                    continue

                with open(result_path, "r", encoding="utf-8") as rf:
                    chunk_results = json.load(rf)

                original_descriptions = {}
                if os.path.exists(chunk_path):
                    with open(chunk_path, "r", encoding="utf-8") as cf:
                        original_rows = json.load(cf)
                    for j, row in enumerate(original_rows):
                        original_descriptions[j] = row.get(desc_col, "")

                for j, result in enumerate(chunk_results):
                    item = {
                        "index": global_index,
                        "description": result.get("description") or original_descriptions.get(j, ""),
                        "N1": result.get("N1", "Nao Identificado"),
                        "N2": result.get("N2", "Nao Identificado"),
                        "N3": result.get("N3", "Nao Identificado"),
                        "N4": result.get("N4", "Nao Identificado"),
                        "confidence": result.get("confidence", 0.0),
                        "source": result.get("source", ""),
                        "status": result.get("status", "") or (
                            "Nenhum" if any(
                                str(result.get(lvl, "")).strip() in ("", "Não Identificado", "Nao Identificado")
                                for lvl in ("N1", "N2", "N3", "N4")
                            ) else "Unico"
                        ),
                    }
                    items.append(item)
                    global_index += 1

        logger.info(f"[GetJobResults] Job {job_id}: status={job_status}, items={len(items)}")

        response = {
            "jobId": job_id,
            "status": job_status,
            "items": items,
            "total": len(items),
            "analytics": analytics,
            "summary": summary,
        }

        return func.HttpResponse(
            body=safe_json_dumps(response),
            status_code=200,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    except Exception as e:
        logger.error(f"GetJobResults error: {e}", exc_info=True)
        return func.HttpResponse(f"Error reading job results: {e}", status_code=500)
