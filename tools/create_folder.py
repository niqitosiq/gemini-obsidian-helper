import os
import logging
from .utils import _resolve_vault_path

logger = logging.getLogger(__name__)


def create_folder(folder_path: str) -> dict:
    """Creates a new folder (directory) within the Obsidian vault."""
    logger.info(f"Attempting to create folder: {folder_path}")
    safe_path = _resolve_vault_path(folder_path)

    if not safe_path:
        return {
            "status": "error",
            "message": f"Invalid or unsafe folder path: {folder_path}",
        }

    try:
        # exist_ok=True prevents error if folder already exists
        os.makedirs(safe_path, exist_ok=True)
        logger.info(f"Successfully ensured folder exists: {safe_path}")
        return {
            "status": "success",
            "message": f"Folder '{folder_path}' created or already exists.",
        }

    except OSError as e:
        logger.error(f"OS error creating folder '{safe_path}': {e}", exc_info=True)
        return {"status": "error", "message": f"OS error creating folder: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error creating folder '{safe_path}': {e}", exc_info=True
        )
        return {"status": "error", "message": f"Unexpected error creating folder: {e}"}
