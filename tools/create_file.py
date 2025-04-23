import os
import logging
from .utils import _resolve_vault_path

logger = logging.getLogger(__name__)


def create_file(file_path: str, content: str) -> dict:
    """
    Creates a new file with specified content within the Obsidian vault.
    Assumes 'content' includes both frontmatter (if any) and markdown.
    """
    logger.info(f"Attempting to create file: {file_path}")
    safe_path = _resolve_vault_path(file_path)

    if not safe_path:
        return {
            "status": "error",
            "message": f"Invalid or unsafe file path: {file_path}",
        }

    try:
        # Ensure the directory exists
        dir_name = os.path.dirname(safe_path)
        os.makedirs(dir_name, exist_ok=True)

        # Check if file already exists (optional, could overwrite or fail)
        if os.path.exists(safe_path):
            logger.warning(f"File already exists, overwriting: {safe_path}")
            # return {"status": "error", "message": f"File already exists: {file_path}"}

        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Successfully created file: {safe_path}")
        return {
            "status": "success",
            "message": f"File '{file_path}' created successfully.",
        }

    except OSError as e:
        logger.error(f"OS error creating file '{safe_path}': {e}", exc_info=True)
        return {"status": "error", "message": f"OS error creating file: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error creating file '{safe_path}': {e}", exc_info=True
        )
        return {"status": "error", "message": f"Unexpected error creating file: {e}"}
