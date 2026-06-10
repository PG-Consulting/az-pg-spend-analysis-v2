"""Blueprint for taxonomy classification endpoints."""

import os
import json
import io
import base64
import logging
import math
import uuid
from datetime import datetime, timezone

import azure.functions as func
from src.utils import (
    get_models_dir,
    get_jobs_dir,
    friendly_source_label,
    INCOMPLETE_VALUES,
)
from src.api_helpers import (
    json_response,
    options_response,
    handle_errors,
    rate_limit,
)
from src.exceptions import NotFoundError, ValidationError, ConflictError
from src.validation import safe_resource_id
from src.file_lock import read_status, locked_status
from src.auth import require_auth

logger = logging.getLogger(__name__)
classification_bp = func.Blueprint()

CHUNK_SIZE = 500
MAX_UPLOAD_ROWS = 100_000


def _derive_status(row: dict) -> str:
    """Derive classification status from N1-N4 values.

    Returns the existing status if present, otherwise:
    - "Nenhum" if any level is empty or "Não Identificado"
    - "Único" if all levels are identified
    """
    existing = row.get("status", "")
    if existing:
        return existing
    if any(
        str(row.get(lvl, "")).strip() in INCOMPLETE_VALUES
        for lvl in ("N1", "N2", "N3", "N4")
    ):
        return "Nenhum"
    return "Único"


@classification_bp.route(
    route="SubmitTaxonomyJob",
    methods=["POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("SubmitTaxonomyJob")
@require_auth
@rate_limit(requests=10, window=60)
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
        return options_response(req, "POST, OPTIONS")

    logger.info("SubmitTaxonomyJob HTTP trigger processed a request.")

    try:
        req_body = req.get_json()
    except ValueError:
        raise ValidationError("Invalid JSON body")

    file_content_b64 = req_body.get("fileContent")
    if not file_content_b64:
        raise ValidationError("Missing fileContent")

    models_dir = get_models_dir()
    jobs_dir = get_jobs_dir()

    # --- Resolve sector and project context ---
    project_id_raw = req_body.get("projectId", "").strip()
    project_id = (
        safe_resource_id(project_id_raw, field="projectId") if project_id_raw else ""
    )
    client_context = req_body.get("clientContext", "")
    custom_hierarchy_b64 = req_body.get("customHierarchy")  # legacy path
    project_config = None

    if project_id:
        # New path: load project config, resolve hierarchy
        from src.project_manager import get_project, resolve_hierarchy

        project_config = get_project(project_id, models_dir)
        if project_config is None:
            raise NotFoundError("Project", project_id)
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
    else:
        # Legacy path: sector from body
        sector = safe_resource_id(
            req_body.get("sector", ""), field="sector"
        ).capitalize()
        custom_hierarchy_list = None  # will be parsed by worker from b64

    # --- Create job directory ---
    session_id = str(uuid.uuid4())
    job_dir = os.path.join(jobs_dir, session_id)
    os.makedirs(job_dir, exist_ok=True)
    logger.info(f"[Submit] Job {session_id} created at {job_dir}")

    # --- Decode and load file ---
    file_bytes = base64.b64decode(file_content_b64)
    try:
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception:
            try:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    sep=";",
                    encoding="utf-8",
                    on_bad_lines="skip",
                )
            except Exception:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    sep=",",
                    encoding="utf-8",
                    on_bad_lines="skip",
                )
    except Exception as e:
        import shutil

        shutil.rmtree(job_dir, ignore_errors=True)
        raise ValidationError(f"Formato de arquivo invalido: {e}")

    if len(df) > MAX_UPLOAD_ROWS:
        import shutil

        shutil.rmtree(job_dir, ignore_errors=True)
        raise ValidationError(
            f"Arquivo excede o limite de {MAX_UPLOAD_ROWS:,} linhas "
            f"({len(df):,} linhas). Divida o arquivo em partes menores."
        )

    # Identify description column (second non-unnamed column heuristic, same as v2)
    valid_cols = [c for c in df.columns if not str(c).startswith("Unnamed")]
    if len(valid_cols) < 2:
        raise ValidationError("Invalid file columns.")
    desc_col = valid_cols[1]

    # Sort by description to group similar items in the same LLM batch
    df = df.sort_values(
        by=desc_col, key=lambda s: s.str.lower().fillna(""), na_position="last"
    ).reset_index(drop=True)

    # --- Chunking ---
    num_chunks = math.ceil(len(df) / CHUNK_SIZE)

    id_col = valid_cols[0]

    # Build metadata / status
    metadata = {
        "job_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "PENDING",
        "sector": sector,
        "filename": req_body.get("originalFilename", "upload.xlsx"),
        "id_column": id_col,
        "desc_column": desc_col,
        "total_rows": len(df),
        "total_chunks": num_chunks,
        "processed_chunks": 0,
        "client_context": client_context,
        "dictionary_content_b64": req_body.get("dictionaryContent"),
        # Project-based fields
        "project_id": project_id or None,
        "use_web_search": bool(req_body.get("useWebSearch", False)),
        "extra_columns": [
            c
            for c in valid_cols[2:]
            if c
            not in {
                "N1",
                "N2",
                "N3",
                "N4",
                "Fonte",
                "Descricao",
                "Descrição",
                "source",
                "confidence",
                "description",
                "description_norm",
                "classification_source",
                "status",
                "matched_terms",
                "index",
            }
        ],
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
        chunk_df = df.iloc[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        chunk_path = os.path.join(job_dir, f"chunk_{i}.json")
        chunk_df.to_json(chunk_path, orient="records")

    # --- Save status file ---
    with open(os.path.join(job_dir, "status.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)

    # Enqueue job for queue-triggered processing
    from src.queue_helpers import enqueue_job

    enqueued = enqueue_job(session_id)

    response_data = {
        "jobId": session_id,
        "status": "PENDING",
        "total_chunks": num_chunks,
    }
    if not enqueued:
        response_data["warning"] = (
            "Job criado mas não enfileirado. "
            "Será processado pelo cleanup automático (até 1h)."
        )

    return json_response(response_data, status_code=202, request=req)


@classification_bp.route(
    route="GetTaxonomyJobStatus",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetTaxonomyJobStatus")
@require_auth
def GetTaxonomyJobStatus(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetTaxonomyJobStatus?jobId=xxx
    Polls the status of a specific job.
    Returns: status (PENDING/PROCESSING/COMPLETED/ERROR), progress %, and result if done.
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    job_id = safe_resource_id(req.params.get("jobId", ""), field="jobId")

    jobs_dir = get_jobs_dir()
    job_dir = os.path.join(jobs_dir, job_id)
    status_file = os.path.join(job_dir, "status.json")

    if not os.path.exists(status_file):
        raise NotFoundError("Job", job_id)

    status = read_status(status_file)

    # Calculate progress
    total = status.get("total_chunks", 1)
    processed = status.get("processed_chunks", 0)
    pct = (
        min(int((processed / total) * 100), 99)
        if status["status"] != "COMPLETED"
        else 100
    )

    if status["status"] == "PROCESSING":
        total_rows = status.get("total_rows", total * CHUNK_SIZE)
        items_done = min(processed * CHUNK_SIZE, total_rows)
        message = f"{items_done:,} de {total_rows:,} itens processados"
    elif status["status"] == "PENDING":
        message = "Aguardando inicio do processamento..."
    elif status["status"] == "ERROR":
        # Mensagem real do erro (créditos xAI, poison, expiração) em vez do
        # literal "ERROR" — o frontend exibe isso ao consultor.
        message = status.get("error") or "ERROR"
    else:
        message = status["status"]

    response = {
        "jobId": job_id,
        "status": status["status"],
        "progress_pct": pct,
        "message": message,
    }

    if status.get("error"):
        response["error"] = status["error"]

    if status["status"] == "COMPLETED":
        result_file = os.path.join(job_dir, "result.json")
        if os.path.exists(result_file):
            with open(result_file, "r", encoding="utf-8") as rf:
                response.update(json.load(rf))
        else:
            response["status"] = "ERROR"
            response["message"] = "Result file missing."

    return json_response(response, request=req)


@classification_bp.route(
    route="CancelJob", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS
)
@handle_errors("CancelJob")
@require_auth
def CancelJob(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/CancelJob?jobId=xxx
    Cancels a PENDING or PROCESSING job by writing CANCELLED to status.json.
    Returns 200 with {jobId, status: "CANCELLED"}.
    """
    if req.method == "OPTIONS":
        return options_response(req, "POST, OPTIONS")

    job_id = safe_resource_id(req.params.get("jobId", ""), field="jobId")

    jobs_dir = get_jobs_dir()
    job_dir = os.path.join(jobs_dir, job_id)
    status_file = os.path.join(job_dir, "status.json")

    if not os.path.exists(status_file):
        raise NotFoundError("Job", job_id)

    with locked_status(status_file) as status:
        current_status = status.get("status", "")
        if current_status not in ("PENDING", "PROCESSING"):
            raise ConflictError(
                f"Cannot cancel job with status '{current_status}'. "
                "Only PENDING or PROCESSING jobs can be cancelled."
            )
        status["status"] = "CANCELLED"
        status["cancelled_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"[CancelJob] Job {job_id} cancelled (was {current_status})")

    return json_response({"jobId": job_id, "status": "CANCELLED"}, request=req)


@classification_bp.route(
    route="GetJobResults",
    methods=["GET", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("GetJobResults")
@require_auth
def GetJobResults(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/GetJobResults?jobId=xxx
    Returns classified items as a flat JSON array for human review.
    Merges all result_X.json files from the job directory.

    Returns: {jobId, status, items: [{index, description, N1, N2, N3, N4,
              confidence, source, status}], total}
    """
    if req.method == "OPTIONS":
        return options_response(req, "GET, OPTIONS")

    job_id = safe_resource_id(req.params.get("jobId", ""), field="jobId")

    jobs_dir = get_jobs_dir()
    job_dir = os.path.join(jobs_dir, job_id)
    status_file = os.path.join(job_dir, "status.json")

    if not os.path.isdir(job_dir) or not os.path.exists(status_file):
        raise NotFoundError("Job", job_id)

    status_data = read_status(status_file)

    job_status = status_data.get("status", "UNKNOWN")
    total_chunks = status_data.get("total_chunks", 0)
    desc_col = status_data.get("desc_column", "Descricao")
    extra_columns = status_data.get("extra_columns", [])

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
            item = {
                "index": idx,
                "description": row.get(desc_col, row.get("description", "")),
                "N1": row.get("N1", "Não Identificado"),
                "N2": row.get("N2", "Não Identificado"),
                "N3": row.get("N3", "Não Identificado"),
                "N4": row.get("N4", "Não Identificado"),
                "confidence": row.get("confidence", 0.0),
                "source": row.get("source", ""),
                "status": _derive_status(row),
            }
            for col in extra_columns:
                item[col] = row.get(col, "")
            items.append(item)
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
                    "description": result.get("description")
                    or original_descriptions.get(j, ""),
                    "N1": result.get("N1", "Não Identificado"),
                    "N2": result.get("N2", "Não Identificado"),
                    "N3": result.get("N3", "Não Identificado"),
                    "N4": result.get("N4", "Não Identificado"),
                    "confidence": result.get("confidence", 0.0),
                    "source": result.get("source", ""),
                    "status": _derive_status(result),
                }
                items.append(item)
                global_index += 1

    logger.info(
        f"[GetJobResults] Job {job_id}: status={job_status}, items={len(items)}"
    )

    response = {
        "jobId": job_id,
        "status": job_status,
        "items": items,
        "total": len(items),
        "extra_columns": extra_columns,
        "analytics": analytics,
        "summary": summary,
    }

    return json_response(response, request=req)


@classification_bp.route(
    route="DownloadJobExcel",
    methods=["GET", "POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@handle_errors("DownloadJobExcel")
@require_auth
def DownloadJobExcel(req: func.HttpRequest) -> func.HttpResponse:
    """GET/POST /api/DownloadJobExcel?jobId=xxx
    GET: Returns raw classified results as Excel.
    POST: Merges review decisions into results, adds Status column.
    Only works for CLASSIFIED, APPROVED, or COMPLETED jobs.
    """
    import pandas as pd

    if req.method == "OPTIONS":
        return options_response(req, "GET, POST, OPTIONS")

    job_id = safe_resource_id(req.params.get("jobId", ""), field="jobId")

    jobs_dir = get_jobs_dir()
    job_dir = os.path.join(jobs_dir, job_id)
    status_file = os.path.join(job_dir, "status.json")

    if not os.path.isdir(job_dir) or not os.path.exists(status_file):
        raise NotFoundError("Job", job_id)

    status_data = read_status(status_file)

    job_status = status_data.get("status", "UNKNOWN")
    if job_status not in ("CLASSIFIED", "COMPLETED", "APPROVED"):
        raise ValidationError(
            f"Job com status '{job_status}' não pode ser baixado. "
            "Apenas jobs CLASSIFIED, APPROVED ou COMPLETED."
        )

    result_file = os.path.join(job_dir, "result.json")
    if not os.path.exists(result_file):
        raise NotFoundError("Result file", job_id)

    with open(result_file, "r", encoding="utf-8") as rf:
        result_json = json.load(rf)

    id_col = status_data.get("id_column")
    desc_col = status_data.get("desc_column", "Descricao")
    extra_columns = status_data.get("extra_columns", [])
    raw_items = result_json.get("items", [])

    # Parse decisions from POST body (if present)
    decisions = None
    decision_map = {}
    if req.method == "POST":
        try:
            body = req.get_json()
            decisions = body.get("decisions", [])
        except (ValueError, AttributeError):
            decisions = []

        # Validate decisions
        valid_decisions = ("approved", "edited", "rejected")
        if len(decisions) > len(raw_items):
            raise ValidationError(
                f"Mais decisions ({len(decisions)}) que itens ({len(raw_items)})."
            )
        for d in decisions:
            idx = d.get("index")
            dec = d.get("decision")
            if not isinstance(idx, int) or idx < 0 or idx >= len(raw_items):
                raise ValidationError(
                    f"Decision index inválido: {idx} (total itens: {len(raw_items)})"
                )
            if dec not in valid_decisions:
                raise ValidationError(
                    f"Decision inválida: '{dec}'. Esperado: {valid_decisions}"
                )
            decision_map[idx] = d  # último ganha em caso de duplicata

    _STATUS_LABELS = {
        "approved": "Aprovado",
        "edited": "Editado",
        "rejected": "Rejeitado",
    }

    rows = []
    for idx, item in enumerate(raw_items):
        row = {}
        if id_col:
            row[id_col] = item.get(id_col, "")
        row["Descricao"] = item.get(desc_col, item.get("description", ""))
        for col in extra_columns:
            row[col] = item.get(col, "")

        d = decision_map.get(idx)
        if d and d["decision"] == "edited":
            row["N1"] = d.get("N1", "")
            row["N2"] = d.get("N2", "")
            row["N3"] = d.get("N3", "")
            row["N4"] = d.get("N4", "")
            row["Fonte"] = "Ajuste Manual"
        else:
            row["N1"] = item.get("N1", "")
            row["N2"] = item.get("N2", "")
            row["N3"] = item.get("N3", "")
            row["N4"] = item.get("N4", "")
            if decisions is not None:
                # POST: result.json já tem labels amigáveis — usar direto
                row["Fonte"] = item.get("source", "")
            else:
                # GET: backward compat — chama friendly_source_label
                row["Fonte"] = friendly_source_label(item.get("source", ""))

        # Coluna Status só no POST
        if decisions is not None:
            if d:
                row["Status"] = _STATUS_LABELS.get(d["decision"], "Pendente")
            else:
                row["Status"] = "Pendente"

        rows.append(row)

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Resultados", engine="openpyxl")
    excel_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    original_filename = status_data.get("filename", "resultado.xlsx")
    base_name = os.path.splitext(original_filename)[0]
    output_filename = f"{base_name}_resultado.xlsx"

    logger.info(
        f"[DownloadJobExcel] Job {job_id}: {len(rows)} rows, file={output_filename}"
    )

    return json_response(
        {
            "filename": output_filename,
            "file_content_base64": excel_b64,
        },
        request=req,
    )
