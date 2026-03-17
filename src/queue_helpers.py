"""Queue helper for enqueuing taxonomy jobs to Azure Storage Queue."""

import json
import logging
import os

logger = logging.getLogger(__name__)

QUEUE_NAME = "taxonomy-jobs"


def enqueue_job(job_id: str) -> bool:
    """Enqueue a job message to the taxonomy-jobs queue.

    Returns True if enqueued successfully, False on any failure.
    The cleanup timer serves as safety net for failed enqueues.
    """
    try:
        from azure.storage.queue import QueueClient
    except ImportError:
        logger.error(
            "[Queue] azure-storage-queue não instalado. "
            "Instale com: pip install azure-storage-queue"
        )
        return False

    conn_str = os.environ.get("AzureWebJobsStorage", "")
    if not conn_str:
        logger.error(
            "[Queue] AzureWebJobsStorage não configurado — job não enfileirado"
        )
        return False

    try:
        queue_client = QueueClient.from_connection_string(conn_str, QUEUE_NAME)
        try:
            queue_client.create_queue()
        except Exception:
            pass  # queue já existe — ok
        message = json.dumps({"job_id": job_id})
        queue_client.send_message(message)
        logger.info(f"[Queue] Job {job_id} enfileirado com sucesso")
        return True
    except Exception as e:
        logger.error(f"[Queue] Falha ao enfileirar job {job_id}: {e}")
        return False
