import logging
import config
from datetime import datetime
from typing import Union

logger = logging.getLogger(__name__)
KB_FILE = config.KNOWLEDGE_BASE_PATH


def log_entry(entry_type: str, content: Union[str, dict]) -> None:
    """Adds an entry to the knowledge base file."""
    try:
        with open(KB_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"## {entry_type.capitalize()} [{timestamp}]\n")
            if isinstance(content, dict):
                for key, value in content.items():
                    f.write(f"- {key}: {value}\n")
            else:
                processed_content = " ".join(content.splitlines())
                f.write(f"- {processed_content}\n")
            f.write("\n")
        logger.debug(f"Entry '{entry_type}' added to knowledge base.")
    except IOError as e:
        logger.error(
            f"Error writing to knowledge base file {KB_FILE}: {e}", exc_info=True
        )


def read_knowledge_base(context_level: str = config.GEMINI_CONTEXT_LEVEL) -> str:
    """Reads knowledge base according to context level."""
    if context_level == "none":
        return ""
    try:
        with open(KB_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        logger.debug(f"Knowledge base read ({len(content)} characters).")

        if context_level in ["maximal", "with_full_kb", "with_kb_sections", "basic"]:
            return content
        else:
            return ""

    except FileNotFoundError:
        logger.warning(
            f"Knowledge base file {KB_FILE} not found. Will be created on first write."
        )
        return ""
    except IOError as e:
        logger.error(f"Error reading knowledge base file {KB_FILE}: {e}", exc_info=True)
        return ""
