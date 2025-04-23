import os
import shutil
import logging
from .utils import _resolve_vault_path
from config import OBSIDIAN_VAULT_PATH

logger = logging.getLogger(__name__)


def delete_folder(folder_path: str) -> dict:
    """Deletes a specified folder (directory) recursively within the Obsidian vault."""
    logger.info(f"Attempting to delete folder: {folder_path}")
    safe_path = _resolve_vault_path(folder_path)

    if not safe_path:
        return {
            "status": "error",
            "message": f"Invalid or unsafe folder path: {folder_path}",
        }

    # Critical Safety Check: Do not delete the vault root!
    vault_root = os.path.abspath(OBSIDIAN_VAULT_PATH)
    if safe_path == vault_root:
        logger.error(
            f"Safety Error: Attempted to delete the vault root directory: {safe_path}"
        )
        return {"status": "error", "message": "Cannot delete the vault root directory."}

    try:
        if not os.path.exists(safe_path):
            logger.error(f"Folder not found for deletion: {safe_path}")
            return {"status": "error", "message": f"Folder not found: {folder_path}"}

        if not os.path.isdir(safe_path):
            logger.error(f"Path is not a directory, cannot delete: {safe_path}")
            return {
                "status": "error",
                "message": f"Path is not a directory: {folder_path}",
            }

        shutil.rmtree(safe_path)
        logger.info(f"Successfully deleted folder: {safe_path}")
        return {
            "status": "success",
            "message": f"Folder '{folder_path}' deleted successfully.",
        }

    except OSError as e:
        logger.error(f"OS error deleting folder '{safe_path}': {e}", exc_info=True)
        return {"status": "error", "message": f"OS error deleting folder: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error deleting folder '{safe_path}': {e}", exc_info=True
        )
        return {"status": "error", "message": f"Unexpected error deleting folder: {e}"}
