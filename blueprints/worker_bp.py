"""Timer-triggered worker blueprint for async taxonomy job processing."""
import logging

import azure.functions as func

logger = logging.getLogger(__name__)
worker_bp = func.Blueprint()


@worker_bp.timer_trigger(
    schedule="*/15 * * * * *",
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=False,
)
def ProcessTaxonomyWorker(myTimer: func.TimerRequest) -> None:
    """Timer trigger fires every 15 seconds.

    Delegates all processing to src.worker_helpers.run_worker_cycle(), which implements:
    - Auto-cleanup of stale PROCESSING jobs (> 1 hour -> ERROR)
    - Round-robin parallel chunk processing (up to 5 chunks simultaneously across all active jobs)
    - Consolidation of fully-processed jobs into a final Excel file
    - Status transitions: PENDING -> PROCESSING -> CLASSIFIED (review pending) / ERROR

    The job queue lives in {models_dir}/taxonomy_jobs/ (one subdirectory per job).
    """
    if myTimer.past_due:
        logger.info("[Worker] Timer is past due, running anyway.")

    try:
        from src.worker_helpers import run_worker_cycle
        run_worker_cycle()
    except Exception as e:
        import traceback
        logger.error(
            f"[Worker] Unhandled error in ProcessTaxonomyWorker: {e}\n{traceback.format_exc()}"
        )
