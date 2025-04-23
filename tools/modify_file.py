import os
import logging
from .utils import _resolve_vault_path

logger = logging.getLogger(__name__)


def modify_file(file_path: str, content: str) -> dict:
    """
    Modifies an existing file within the Obsidian vault by completely
    overwriting its content with the provided content_description.
    The content_description should contain the full desired content,
    including any YAML frontmatter if needed.
    """
    logger.info(f"Attempting to overwrite file: {file_path}")
    safe_path = _resolve_vault_path(file_path)

    if not safe_path:
        return {
            "status": "error",
            "message": f"Invalid or unsafe file path: {file_path}",
        }

    try:
        # Check if the path exists and is a file before attempting to overwrite
        # This prevents accidentally creating a file if it doesn't exist,
        # aligning with the 'modify' intent.
        if not os.path.exists(safe_path):
            logger.error(f"File not found for content: {safe_path}")
            return {"status": "error", "message": f"File not found: {file_path}"}
        if not os.path.isfile(safe_path):
            logger.error(f"Path is not a file, cannot modify: {safe_path}")
            return {"status": "error", "message": f"Path is not a file: {file_path}"}

        # Write the new content, overwriting the existing file
        with open(safe_path, "w", encoding="utf-8") as f:
            # The content is now the full content
            f.write(content)

        logger.info(f"Successfully overwrote file: {safe_path}")
        return {
            "status": "success",
            "message": f"File '{file_path}' content successfully overwritten.",
        }

    except OSError as e:
        logger.error(f"OS error modifying file '{safe_path}': {e}", exc_info=True)
        return {"status": "error", "message": f"OS error modifying file: {e}"}
    except Exception as e:
        logger.error(
            f"Unexpected error modifying file '{safe_path}': {e}", exc_info=True
        )
        return {"status": "error", "message": f"Unexpected error modifying file: {e}"}
