import os
import logging
from typing import Union
from config import OBSIDIAN_VAULT_PATH

logger = logging.getLogger(__name__)


def _resolve_vault_path(relative_path: str) -> Union[str, None]:
    """
    Resolves a relative path within the Obsidian vault path.

    Args:
        relative_path: The relative path provided by the LLM.

    Returns:
        The absolute, normalized path if it's safely within the vault, otherwise None.
    """
    if not OBSIDIAN_VAULT_PATH:
        logger.error("OBSIDIAN_VAULT_PATH is not configured. Cannot resolve path.")
        return None

    # Clean the relative path to prevent trivial traversals like "/foo"
    clean_relative_path = relative_path.strip().lstrip("/")

    # Join with the base vault path
    base_path = os.path.abspath(OBSIDIAN_VAULT_PATH)
    unsafe_path = os.path.join(base_path, clean_relative_path)

    # Normalize the path (resolves .., ., // etc.)
    resolved_path = os.path.normpath(unsafe_path)

    # Security Check: Ensure the resolved path is still within the vault directory
    if os.path.commonpath([base_path]) == os.path.commonpath(
        [base_path, resolved_path]
    ):
        return resolved_path
    else:
        logger.error(
            f"Path traversal attempt detected or path resolved outside vault: '{relative_path}' resolved to '{resolved_path}' which is outside '{base_path}'"
        )
        return None


def _parse_file_content(content: str) -> tuple[str, str]:
    """
    Parses file content into frontmatter (as string) and markdown content.
    Assumes frontmatter is enclosed in '---'.
    """
    parts = content.split("---", 2)
    if len(parts) == 3 and parts[0] == "":
        # Found frontmatter
        frontmatter = parts[1].strip()
        markdown_content = parts[2].strip()
        return frontmatter, markdown_content
    else:
        # No valid frontmatter found, treat everything as content
        return "", content.strip()


def _format_file_content(frontmatter: str, markdown_content: str) -> str:
    """Formats frontmatter string and markdown content back into file string."""
    if frontmatter:
        return f"---\n{frontmatter}\n---\n\n{markdown_content}\n"
    else:
        return f"{markdown_content}\n"
