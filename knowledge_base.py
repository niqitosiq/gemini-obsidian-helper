import logging
import os
from datetime import datetime
import config

logger = logging.getLogger(__name__)


# --- MODIFIED: Function signature and formatting ---
def log_entry(source: str, message: str):
    """Logs a message entry to the knowledge base file in chat format."""
    if not config.KNOWLEDGE_BASE_ENABLED:
        return

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Format as Markdown heading with timestamp, source, and message
        log_line = f"## [{timestamp}] {source}: {message}\n\n"

        with open(config.KNOWLEDGE_BASE_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
        # logger.debug(f"Logged to knowledge base: {source}: {message[:50]}...") # Optional: keep debug log
    except Exception as e:
        logger.error(f"Failed to write to knowledge base: {e}", exc_info=True)


# --- MODIFIED: read_knowledge_base remains largely the same, but might need adjustment
# if the context assembly expects the old format. For now, keep it simple. ---
def read_knowledge_base() -> str:
    """Reads the entire content of the knowledge base file."""
    if not config.KNOWLEDGE_BASE_ENABLED or not os.path.exists(
        config.KNOWLEDGE_BASE_FILE
    ):
        return None
    try:
        with open(config.KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read knowledge base: {e}", exc_info=True)
        return None


def clear_knowledge_base():
    """Clears the knowledge base file."""
    if not config.KNOWLEDGE_BASE_ENABLED:
        logger.warning("Knowledge base is disabled, cannot clear.")
        return
    try:
        with open(config.KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
            f.write("")  # Write empty string to clear
        logger.info("Knowledge base cleared.")
    except Exception as e:
        logger.error(f"Failed to clear knowledge base: {e}", exc_info=True)
