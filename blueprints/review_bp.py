"""Blueprint for human review endpoints."""
import os
import json
import io
import base64
import logging
import datetime

import azure.functions as func
from src.utils import get_models_dir, get_jobs_dir, friendly_source_label
from src.knowledge_base import KnowledgeBase, merge_kb_entries
from src.api_helpers import json_response, error_response, handle_errors
from src.exceptions import NotFoundError

logger = logging.getLogger(__name__)
review_bp = func.Blueprint()


@review_bp.route(route="ReclassifyItems", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("ReclassifyItems")
def reclassify_items_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/ReclassifyItems
    Body: {
        jobId: str,
        projectId: str,
        items: [{index, description}],
        instruction: str  # consultant instruction for re-classification
    }
    Returns: {results: [{index, N1, N2, N3, N4, source, confidence}]}
    """
    body = req.get_json()
    job_id = body.get("jobId", "")
    project_id = body.get("projectId", "")
    items = body.get("items", [])
    instruction = body.get("instruction", "")

    if not items:
        return json_response({"results": []})

    models_dir = get_models_dir()

    # Load project context
    from src.project_manager import get_project, resolve_hierarchy
    project = get_project(project_id, models_dir) if project_id else {}
    client_context = project.get("client_context", "") if project else ""
    custom_hierarchy, _ = resolve_hierarchy(project_id, models_dir) if project_id else (None, "padrao")

    # Load KB for few-shot examples (sector + project merged, if use_sector_kb)
    kb_entries = []
    if project_id:
        try:
            project_kb = KnowledgeBase(project_id, models_dir)
            sector_slug = project.get("sector", "") if project else ""
            use_sector_kb = project.get("use_sector_kb", True) if project else True
            sector_entries = []
            if sector_slug and use_sector_kb:
                try:
                    sector_kb = KnowledgeBase(sector_slug, models_dir, entity_type="sector")
                    sector_entries = sector_kb.entries
                except Exception:
                    pass
            kb_entries = merge_kb_entries(sector_entries, project_kb.entries)
        except Exception:
            pass

    # Re-classify with instruction using enriched per-item KB examples
    from src.llm_classifier import classify_items_with_llm
    from src.kb_retriever import KBRetriever

    descriptions = [item["description"] for item in items]

    # Build enriched examples from per-item KB matches (not global)
    retriever = KBRetriever(kb_entries) if kb_entries else None
    enriched_examples = None
    if retriever and retriever.matrix is not None:
        batch_matches = retriever.retrieve_batch(descriptions, top_k=5)
        enriched_examples = KBRetriever.select_enriched_examples(
            batch_matches, max_examples=20
        )
    if not enriched_examples:
        enriched_examples = KBRetriever.select_representative_examples(
            kb_entries, max_k=10
        ) if kb_entries else None

    llm_results = classify_items_with_llm(
        descriptions,
        sector=project.get("sector", "Padrao") if project else "Padrao",
        client_context=client_context,
        custom_hierarchy=custom_hierarchy,
        few_shot_examples=enriched_examples,
        user_instruction=instruction,
    )

    # Merge results with original indices
    results = []
    for i, item in enumerate(items):
        r = llm_results[i] if i < len(llm_results) and llm_results[i] else {}
        results.append({
            "index": item.get("index", i),
            "description": item["description"],
            "N1": r.get("N1", "Não Identificado"),
            "N2": r.get("N2", "Não Identificado"),
            "N3": r.get("N3", "Não Identificado"),
            "N4": r.get("N4", "Não Identificado"),
            "source": r.get("source", "LLM (Reclassified)"),
            "confidence": r.get("confidence", 0.0),
            "status": r.get("status", "Único"),
        })

    return json_response({"results": results})


@review_bp.route(route="ApproveClassifications", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@handle_errors("ApproveClassifications")
def approve_classifications_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/ApproveClassifications
    Body: {
        jobId: str,
        projectId: str,
        decisions: [{
            index: int,
            description: str,
            decision: 'approved'|'edited'|'rejected',
            N1, N2, N3, N4: str,  # final values
            confidence: float,
            source: str,
            contribute_to_kb: bool
        }]
    }

    Actions:
    1. Feed approved/edited items to KB (if contribute_to_kb=True or decision='edited')
    2. Update job result files with final decisions
    3. Generate approved Excel
    4. Update job status to COMPLETED

    Returns: {success, kb_added, summary, download_filename, file_content_base64}
    """
    body = req.get_json()
    job_id = body.get("jobId", "")
    project_id = body.get("projectId", "")
    decisions = body.get("decisions", [])

    models_dir = get_models_dir()
    jobs_dir = get_jobs_dir()
    job_dir = os.path.join(jobs_dir, job_id)

    if not os.path.isdir(job_dir):
        raise NotFoundError("Job", job_id)

    # 1. Feed approved/edited items to KB
    kb_added = 0
    if project_id:
        kb_entries_to_add = []
        _incomplete = {"", "Não Identificado", "Não Identificado"}
        for d in decisions:
            if d.get("decision") in ("approved", "edited") and (
                d.get("contribute_to_kb", True) or d.get("decision") == "edited"
            ):
                # Skip entries with incomplete classification (any N-level is "Não Identificado")
                if any(
                    str(d.get(lvl, "")).strip() in _incomplete
                    for lvl in ("N1", "N2", "N3", "N4")
                ):
                    continue
                source = "consultant_correction" if d.get("decision") == "edited" else "llm_approved"
                kb_entries_to_add.append({
                    "description": d.get("description", ""),
                    "N1": d.get("N1", ""),
                    "N2": d.get("N2", ""),
                    "N3": d.get("N3", ""),
                    "N4": d.get("N4", ""),
                    "source": source,
                    "confidence": d.get("confidence", 0.85) if source == "llm_approved" else 1.0,
                    "instruction_used": d.get("instruction_used"),
                })
        if kb_entries_to_add:
            try:
                kb = KnowledgeBase(project_id, models_dir)
                kb_added = kb.add_entries(kb_entries_to_add)
                # Only create snapshot if entries were actually added/updated
                if kb_added > 0:
                    kb.create_version_snapshot()
            except Exception as e:
                logger.warning(f"KB update failed: {e}")

    # 2. Generate approved Excel from decisions
    import pandas as pd

    # Load status.json + result.json to recover the ID column (SKU) per item index
    status_path = os.path.join(job_dir, "status.json")
    with open(status_path, "r", encoding="utf-8") as f:
        status_data = json.load(f)
    id_col = status_data.get("id_column")
    id_lookup = {}
    result_path = os.path.join(job_dir, "result.json")
    if id_col and os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as rf:
            result_tmp = json.load(rf)
        for idx, item in enumerate(result_tmp.get("items", [])):
            id_lookup[idx] = item.get(id_col, "")

    rows = []
    for d in decisions:
        if d.get("decision") != "rejected":
            row = {}
            if id_col:
                row[id_col] = id_lookup.get(d.get("index", -1), "")
            row["Descrição"] = d.get("description", "")
            row["N1"] = d.get("N1", "")
            row["N2"] = d.get("N2", "")
            row["N3"] = d.get("N3", "")
            row["N4"] = d.get("N4", "")
            row["Fonte"] = friendly_source_label(d.get("source", ""))
            rows.append(row)

    rejected_count = sum(1 for d in decisions if d.get("decision") == "rejected")
    approved_count = sum(1 for d in decisions if d.get("decision") == "approved")
    edited_count = sum(1 for d in decisions if d.get("decision") == "edited")

    df_approved = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_approved.to_excel(writer, index=False, sheet_name="Classificados")
    file_bytes = buf.getvalue()
    file_b64 = base64.b64encode(file_bytes).decode("utf-8")

    # 3. Update job status
    download_filename = None
    if status_data:
        status_data["status"] = "COMPLETED"
        status_data["review_completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        status_data["review_summary"] = {
            "total": len(decisions),
            "approved": approved_count,
            "edited": edited_count,
            "rejected": rejected_count,
            "kb_added": kb_added,
        }
        status_data["approved_file_content_base64"] = file_b64
        original_filename = status_data.get("filename", "upload.xlsx")
        base_name = os.path.splitext(original_filename)[0]
        download_filename = f"{base_name}_classificado.xlsx"
        status_data["approved_download_filename"] = download_filename
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False)

    return json_response({
        "success": True,
        "kb_added": kb_added,
        "summary": {
            "total": len(decisions),
            "approved": approved_count,
            "edited": edited_count,
            "rejected": rejected_count,
            "kb_added": kb_added,
        },
        "download_filename": download_filename if rows else None,
        "file_content_base64": file_b64 if rows else None,
    })
