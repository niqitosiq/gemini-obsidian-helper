import os
import logging
from .utils import _resolve_vault_path

logger = logging.getLogger(__name__)


def delete_file(file_path: str) -> dict:
    """Deletes a specified file within the Obsidian vault."""
    logger.info(f"Attempting to delete file: {file_path}")
    safe_path = _resolve_vault_path(file_path)

    if not safe_path:
        return {
            "status": "error",
            "message": f"Invalid or unsafe file path: {file_path}",
        }

    try:
        if not os.path.exists(safe_path):
            logger.error(f"File not found for deletion: {safe_path}")
            return {"status": "error", "message": f"File not found: {file_path}"}

        if not os.path.isfile(safe_path):
            logger.error(f"Path is not a file, cannot delete: {safe_path}")
            return {"status": "error", "message": f"Path is not a file: {file_path}"}

        os.remove(safe_path)
        logger.info(f"Successfully deleted file: {safe_path}")
        return {
            "status": "success",
            "message": f"File '{file_path}' deleted successfully.",
        }

    except OSError as e:
        logger.error(f"OS error deleting file '{safe_path}': {e}", exc_info=True)
        return {"status": "error", "message": f"OS error deleting file: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error deleting file '{safe_path}': {e}", exc_info=True
        )
        return {"status": "error", "message": f"Unexpected error deleting file: {e}"}
