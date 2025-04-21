import os
import logging
from pathlib import Path
import config

logger = logging.getLogger(__name__)

# Ensure the vault path is absolute and exists
try:
    VAULT_PATH = Path(config.OBSIDIAN_VAULT_PATH).resolve()
    if not VAULT_PATH.is_dir():
        logger.error(
            f"Obsidian vault path does not exist or is not a directory: {VAULT_PATH}"
        )
        # You might want to raise an exception or handle this more gracefully
        VAULT_PATH = None
except AttributeError:
    logger.error("OBSIDIAN_VAULT_PATH is not configured in config.py")
    VAULT_PATH = None
except Exception as e:
    logger.error(f"Error resolving Obsidian vault path: {e}")
    VAULT_PATH = None


def _resolve_vault_path(relative_path: str) -> Path | None:
    """Resolves a relative path within the vault to an absolute path, ensuring it stays within the vault."""
    if not VAULT_PATH:
        logger.error("Vault path is not configured or invalid.")
        return None
    if not relative_path:
        logger.error("Relative path cannot be empty.")
        return None

    try:
        # Normalize the relative path to prevent issues like ".."
        normalized_relative_path = Path(os.path.normpath(relative_path))

        # Ensure the path doesn't start with "/" or drive letters to avoid absolute path interpretation
        if normalized_relative_path.is_absolute():
            logger.error(f"Relative path looks like an absolute path: {relative_path}")
            return None

        absolute_path = (VAULT_PATH / normalized_relative_path).resolve()

        # Security Check: Ensure the resolved path is still within the VAULT_PATH directory
        if VAULT_PATH not in absolute_path.parents and absolute_path != VAULT_PATH:
            logger.error(
                f"Attempted path traversal detected: {relative_path} resolves outside vault {VAULT_PATH}"
            )
            return None

        return absolute_path
    except Exception as e:
        logger.error(f"Error resolving path {relative_path} within vault: {e}")
        return None


def read_vault_file(relative_path: str) -> str | None:
    """Reads the content of a file within the Obsidian vault."""
    absolute_path = _resolve_vault_path(relative_path)
    if not absolute_path:
        return None  # Error logged in _resolve_vault_path

    try:
        if not absolute_path.is_file():
            logger.error(f"File not found or is not a file: {absolute_path}")
            return None
        with open(absolute_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"Successfully read file: {relative_path}")
        return content
    except FileNotFoundError:
        logger.error(f"File not found: {absolute_path}")
        return None
    except Exception as e:
        logger.error(f"Error reading file {relative_path}: {e}", exc_info=True)
        return None


def write_vault_file(relative_path: str, content: str) -> bool:
    """Writes (or overwrites) content to a file within the Obsidian vault."""
    absolute_path = _resolve_vault_path(relative_path)
    if not absolute_path:
        return False  # Error logged in _resolve_vault_path

    try:
        # Ensure the parent directory exists
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        with open(absolute_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Successfully wrote to file: {relative_path}")
        return True
    except Exception as e:
        logger.error(f"Error writing to file {relative_path}: {e}", exc_info=True)
        return False


def append_vault_file(relative_path: str, content: str) -> bool:
    """Appends content to a file within the Obsidian vault."""
    absolute_path = _resolve_vault_path(relative_path)
    if not absolute_path:
        return False  # Error logged in _resolve_vault_path

    try:
        # Ensure the parent directory exists
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        with open(absolute_path, "a", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Successfully appended to file: {relative_path}")
        return True
    except Exception as e:
        logger.error(f"Error appending to file {relative_path}: {e}", exc_info=True)
        return False


def list_vault_files(relative_path: str = ".") -> list[str] | None:
    """Lists files and directories within a specified relative path in the vault."""
    absolute_path = _resolve_vault_path(relative_path)
    if not absolute_path:
        return None  # Error logged in _resolve_vault_path

    if not absolute_path.is_dir():
        logger.error(f"Path is not a directory: {absolute_path}")
        return None

    try:
        entries = []
        for entry in absolute_path.iterdir():
            # Represent directories with a trailing slash
            entry_name = entry.name + "/" if entry.is_dir() else entry.name
            entries.append(entry_name)
        logger.info(f"Successfully listed directory: {relative_path}")
        return entries
    except Exception as e:
        logger.error(f"Error listing directory {relative_path}: {e}", exc_info=True)
        return None


# --- Placeholder for future Semantic Search ---
# def semantic_search_vault(query: str, top_k: int = 5) -> list[dict] | None:
#     logger.warning("Semantic search is not yet implemented.")
#     # 1. Load or connect to index
#     # 2. Generate query embedding
#     # 3. Perform search
#     # 4. Format and return results (e.g., [{'file_path': 'path/to/file.md', 'score': 0.85, 'snippet': '...'}])
#     return None


# --- Placeholder for getting ALL vault content (Use with extreme caution!) ---
def get_all_vault_content(max_total_chars: int = 1000000) -> str | None:
    """
    Reads content from all .md files in the vault up to a maximum character limit.
    WARNING: This can be very slow and memory-intensive for large vaults.
    Use the agentic approach (LLM requesting specific files) whenever possible.
    """
    if not VAULT_PATH:
        logger.error("Vault path is not configured or invalid.")
        return None

    all_content = []
    current_chars = 0
    file_count = 0

    try:
        for md_file in VAULT_PATH.rglob("*.md"):
            if current_chars >= max_total_chars:
                logger.warning(
                    f"Reached max character limit ({max_total_chars}) while reading vault. Content truncated."
                )
                break
            try:
                relative_path = md_file.relative_to(VAULT_PATH)
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    content_len = len(content)

                    # Add file header and content if it fits
                    header = f"\n--- File: {relative_path} ---\n"
                    header_len = len(header)

                    if current_chars + header_len + content_len <= max_total_chars:
                        all_content.append(header)
                        all_content.append(content)
                        current_chars += header_len + content_len
                        file_count += 1
                    elif current_chars + header_len < max_total_chars:
                        # Add header and partial content if possible
                        all_content.append(header)
                        remaining_space = max_total_chars - (current_chars + header_len)
                        all_content.append(
                            content[:remaining_space] + "\n... (truncated)"
                        )
                        current_chars = max_total_chars  # Mark as full
                        file_count += 1
                        logger.warning(f"Truncated content of file: {relative_path}")
                        break  # Stop after truncating one file
                    else:
                        # Not even header fits
                        logger.warning(
                            f"Could not include file {relative_path} due to character limit."
                        )
                        break

            except Exception as read_err:
                logger.error(f"Error reading file {md_file}: {read_err}")
                continue  # Skip this file

        logger.info(
            f"Read content from {file_count} files, total characters: {current_chars}"
        )
        return "".join(all_content)

    except Exception as e:
        logger.error(
            f"Error traversing vault directory {VAULT_PATH}: {e}", exc_info=True
        )
        return None
