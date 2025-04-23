import logging

logger = logging.getLogger(__name__)


def finish() -> dict:
    """
    Placeholder for the finish tool function.
    Indicates the conversation or task is complete. Logs the call.
    """
    logger.info("Tool: finish called")
    # In a real scenario, this might trigger cleanup or state changes.
    return {"status": "finished", "message": "Task marked as finished."}
