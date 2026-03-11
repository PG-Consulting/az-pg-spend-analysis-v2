"""Queue-triggered worker blueprint for async taxonomy job processing."""

import json
import logging
import os
from datetime import datetime, timezone

import azure.functions as func

logger = logging.getLogger(__name__)
worker_bp = func.Blueprint()


@worker_bp.queue_trigger(
    arg_name="msg",
    queue_name="taxonomy-jobs",
    connection="AzureWebJobsStorage",
)
def ProcessTaxonomyJob(msg: func.QueueMessage) -> None:
    """Queue trigger: processes a single taxonomy job to CLASSIFIED.

    Message format: {"job_id": "<uuid>"}

    Re-raises exceptions so the runtime retries via dequeue count
    (maxDequeueCount=5 in host.json). After 5 failures, message goes
    to the taxonomy-jobs-poison queue.
    """
    try:
        payload = json.loads(msg.get_body().decode("utf-8"))
        job_id = payload["job_id"]
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[Worker] Mensagem inválida na queue: {e}")
        return  # não re-raise — mensagem malformada não deve ser retentada

    logger.info(f"[Worker] Queue trigger recebido para job {job_id}")

    from src.worker_helpers import process_single_job

    process_single_job(job_id)


@worker_bp.timer_trigger(
    schedule="0 0 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=False,
)
def CleanupStaleJobs(timer: func.TimerRequest) -> None:
    """Timer trigger: safety net — runs once per hour.

    1. Marks PROCESSING jobs older than 1 hour as ERROR
    2. Re-enqueues orphan PENDING jobs (created > 5 min ago)
    """
    from src.worker_helpers import cleanup_stale_jobs
    from src.utils import get_jobs_dir
    from src.file_lock import read_status
    from src.queue_helpers import enqueue_job

    jobs_root = get_jobs_dir()
    if not os.path.exists(jobs_root):
        return

    # 1. Cleanup stale PROCESSING jobs
    cleanup_stale_jobs(jobs_root)

    # 2. Re-enqueue orphan PENDING jobs
    for job_id in os.listdir(jobs_root):
        status_path = os.path.join(jobs_root, job_id, "status.json")
        if not os.path.exists(status_path):
            continue
        try:
            status = read_status(status_path)
            if status.get("status") != "PENDING":
                continue
            created_at = status.get("created_at", "")
            if not created_at:
                continue
            created = datetime.fromisoformat(created_at)
            elapsed = (datetime.now(timezone.utc) - created).total_seconds()
            if elapsed > 300:  # 5 minutos
                enqueue_job(job_id)
                logger.info(f"[Cleanup] Re-enqueued orphan PENDING job {job_id}")
        except Exception as e:
            logger.error(f"[Cleanup] Erro ao verificar job {job_id}: {e}")
