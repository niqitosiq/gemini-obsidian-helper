import logging
import json
import os
import re
from typing import List, Dict, Any, Optional, Union

import llm_handler

# Import config to access OBSIDIAN_VAULT_PATH
from config import OBSIDIAN_VAULT_PATH

# Ensure tools package imports work correctly after __init__.py changes
from tools import tools, get_tool_definitions

# Import the new prompt builder
from prompt_builder import get_system_prompt
from google.genai import types

logger = logging.getLogger(__name__)

# --- History Persistence ---
_HISTORY_CACHE_FILE = "conversation_history.json"
# In-memory history cache
_conversation_history: List[Dict[str, Any]] = []


def _load_history() -> List[Dict[str, Any]]:
    """Loads conversation history from the cache file."""
    if not os.path.exists(_HISTORY_CACHE_FILE):
        logger.info("History cache file not found. Starting fresh.")
        return []
    try:
        with open(_HISTORY_CACHE_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
            if isinstance(history, list):
                logger.info(f"Loaded {len(history)} entries from history cache.")
                return history
            else:
                logger.warning(
                    "History cache file has invalid format (not a list). Starting fresh."
                )
                return []
    except json.JSONDecodeError:
        logger.error(
            "Error decoding history cache file. Starting fresh.", exc_info=True
        )
        return []
    except Exception as e:
        logger.error(
            f"Error loading history cache file: {e}. Starting fresh.", exc_info=True
        )
        return []


def _save_history():
    """Saves the current conversation history to the cache file."""
    try:
        with open(_HISTORY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_conversation_history, f, indent=2, ensure_ascii=False)
        logger.debug(f"Saved {len(_conversation_history)} entries to history cache.")
    except Exception as e:
        logger.error(f"Error saving history cache file: {e}", exc_info=True)


def _clear_history_cache():
    """Clears the in-memory history and deletes the cache file."""
    global _conversation_history
    _conversation_history = []
    if os.path.exists(_HISTORY_CACHE_FILE):
        try:
            os.remove(_HISTORY_CACHE_FILE)
            logger.info("Cleared history cache file.")
        except Exception as e:
            logger.error(f"Error deleting history cache file: {e}", exc_info=True)
    else:
        logger.info("History cache file already deleted or never existed.")


# --- Message Processing ---


def _build_vault_context() -> Optional[types.Content]:
    """
    Builds a context string containing the path and content of all files
    in the configured Obsidian vault, filtering by allowed extensions.
    """
    if not OBSIDIAN_VAULT_PATH or not os.path.isdir(OBSIDIAN_VAULT_PATH):
        logger.warning(
            "OBSIDIAN_VAULT_PATH is not set or not a valid directory. Skipping vault context."
        )
        return None

    allowed_extensions = ["md"]  # List of allowed extensions for context
    vault_context_parts = []
    vault_root = os.path.abspath(OBSIDIAN_VAULT_PATH)
    logger.info(f"Building context from Obsidian vault: {vault_root}")

    file_count = 0
    total_size = 0

    try:
        for root, _, files in os.walk(vault_root):
            for filename in files:
                # Filter files by allowed extensions
                if not any(filename.endswith(f".{ext}") for ext in allowed_extensions):
                    continue

                file_abs_path = os.path.join(root, filename)
                try:
                    # Calculate relative path for clarity in context
                    relative_path = os.path.relpath(file_abs_path, vault_root)

                    with open(file_abs_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    formatted_file_context = (
                        f"File: {relative_path}\n\n```\n{content}\n```\n\n"
                    )
                    vault_context_parts.append(formatted_file_context)
                    file_count += 1
                    total_size += len(content)

                except Exception as read_err:
                    logger.error(
                        f"Error reading file {file_abs_path} for context: {read_err}",
                        exc_info=True,
                    )

        if not vault_context_parts:
            logger.info("No files found or read from the vault.")
            return None

        vault_full_context_string = "".join(vault_context_parts)
        logger.info(
            f"Built vault context string with {file_count} files, total size ~{total_size} chars."
        )
        # Log a warning about potential size issues
        if total_size > 100000:  # Example threshold
            logger.warning(
                f"Vault context size is large (~{total_size} chars). This may exceed LLM limits or be costly."
            )

        # Use 'user' role to provide this as information to the assistant
        return types.Content(
            role="user", parts=[types.Part(text=vault_full_context_string)]
        )

    except Exception as walk_err:
        logger.error(
            f"Error walking the vault directory {vault_root}: {walk_err}", exc_info=True
        )
        return None


def _prepare_context(user_message: str) -> List[types.Content]:
    """
    Prepares the context for the LLM:
    1. Loads/updates/saves conversation history.
    2. Builds context from Obsidian vault files.
    3. Formats conversation history for the API.
    4. Combines vault context and conversation history.
    """
    global _conversation_history
    # Load history only if the in-memory list is empty (e.g., app start)
    if not _conversation_history:
        _conversation_history = _load_history()

    # Append the new user message (as dict) to the persistent history
    _conversation_history.append({"role": "user", "parts": [{"text": user_message}]})

    # Save updated persistent history (user message added)
    _save_history()

    # Build the vault context (reads files every time, could be cached/optimized)
    vault_context_content = _build_vault_context()

    # Convert persistent history (list of dicts) to list of Content objects for the API
    formatted_api_history = []
    for entry in _conversation_history:
        try:
            # Ensure parts is a list of Part-compatible dicts or strings
            parts_data = entry.get("parts", [])
            if isinstance(parts_data, str):  # Handle simple string content case
                parts_data = [{"text": parts_data}]
            elif isinstance(parts_data, list):
                # Ensure each item in parts is dict-like or string
                processed_parts = []
                for part_item in parts_data:
                    if isinstance(part_item, str):
                        processed_parts.append({"text": part_item})
                    elif isinstance(part_item, dict):
                        # Ensure function call/response parts are correctly structured if needed
                        processed_parts.append(part_item)
                    # else: skip incompatible part types
                parts_data = processed_parts
            else:
                parts_data = []  # Fallback for unexpected types

            # Create Content object, ensuring parts are correctly formatted
            # The google.genai library handles conversion from dicts if structured correctly
            content_entry = types.Content(role=entry.get("role"), parts=parts_data)
            formatted_api_history.append(content_entry)
        except Exception as e:
            logger.error(
                f"Error formatting history entry for API: {entry} - {e}", exc_info=True
            )
            # Optionally skip corrupted entries

    # Combine vault context (if any) and formatted conversation history
    final_context_for_llm = []
    if vault_context_content:
        final_context_for_llm.append(vault_context_content)

    final_context_for_llm.extend(formatted_api_history)

    logger.debug(
        f"Prepared final context with {len(final_context_for_llm)} entries for LLM (including vault context if present)."
    )
    return final_context_for_llm


def _process_llm_response(
    response: Optional[types.GenerateContentResponse],
) -> Optional[Dict[str, Any]]:
    """
    Processes the LLM response.
    1. Extracts text content.
    2. Appends model response to history.
    3. Tries to parse the response text as a JSON array containing a single
       object: [{"tool": "tool_name", "data": {...}}].
    4. Executes the tool if JSON is valid and matches format, appends result
       to history, and handles 'finish'.
    5. Falls back to returning plain text if response is not the expected JSON format.
    6. Saves history.
    """
    global _conversation_history
    if not response:
        logger.error("Received None response from LLM.")
        return {"error": "LLM response was empty."}

    try:
        # Extract text content
        if hasattr(response, "text"):
            llm_text = response.text
        elif response.parts and hasattr(response.parts[0], "text"):
            llm_text = response.parts[0].text
        else:
            logger.error(f"Could not extract text from LLM response: {response}")
            return {"error": "Could not extract text from LLM response."}

        logger.debug(f"LLM raw response text: {llm_text[:500]}...")

        # Append model's raw response to history *before* processing for tools
        _conversation_history.append({"role": "model", "parts": [{"text": llm_text}]})
        # Save history immediately after adding model response
        _save_history()

        # --- JSON Array Tool Call Parsing ---
        try:
            # Attempt to parse the entire response text as JSON
            parsed_response = json.loads(llm_text)

            # Check if we received an array of tool calls
            if not isinstance(parsed_response, list):
                raise ValueError("Expected JSON array of tool calls")

            # Process each tool call in the array
            final_result = None

            for i, tool_call_obj in enumerate(parsed_response):
                if (
                    not isinstance(tool_call_obj, dict)
                    or "tool" not in tool_call_obj
                    or "data" not in tool_call_obj
                ):
                    logger.error(
                        f"Invalid tool call format at position {i}: {tool_call_obj}"
                    )
                    continue

                tool_name = tool_call_obj["tool"]
                tool_args = tool_call_obj["data"]

                logger.info(
                    f"Parsed tool call [{i+1}/{len(parsed_response)}]: {tool_name} with args: {tool_args}"
                )

                # Validate tool name
                if tool_name not in tools:
                    error_msg = f"LLM requested unknown tool: '{tool_name}'"
                    logger.error(error_msg)
                    _conversation_history.append(
                        {
                            "role": "user",
                            "parts": [{"text": f"[Tool Error: {error_msg}]"}],
                        }
                    )
                    _save_history()
                    continue  # Skip to next tool call instead of returning

                # Execute the tool
                try:
                    tool_function = tools[tool_name]
                    logger.info(f"Executing tool '{tool_name}' with args: {tool_args}")
                    tool_result = tool_function(**tool_args)
                    logger.info(f"Tool '{tool_name}' executed. Result: {tool_result}")

                    # Append tool result to history
                    tool_result_str = json.dumps(tool_result, ensure_ascii=False)
                    _conversation_history.append(
                        {
                            "role": "user",
                            "parts": [{"text": f"[Tool response: {tool_result_str}]"}],
                        }
                    )
                    _save_history()

                    # Save the final result (will be overwritten by each successful tool call)
                    final_result = tool_result

                    # Handle 'finish' tool specifically
                    if tool_name == "finish":
                        logger.info("Detected 'finish' tool call. Clearing history.")
                        _clear_history_cache()
                        # For finish, we break early since history is cleared
                        return final_result

                except Exception as e:
                    error_msg = (
                        f"Error executing tool '{tool_name}' with args {tool_args}: {e}"
                    )
                    logger.error(error_msg, exc_info=True)
                    _conversation_history.append(
                        {
                            "role": "user",
                            "parts": [{"text": f"[Tool Execution Error: {error_msg}]"}],
                        }
                    )
                    _save_history()
                    # Continue processing remaining tools instead of returning

            # Return the result of the last successfully executed tool, or None if all failed
            return (
                final_result
                if final_result is not None
                else {"error": "All tool calls failed"}
            )

        except json.JSONDecodeError:
            print(llm_text)
            # --- No Valid JSON Detected ---
            logger.info("LLM response was not valid JSON. Treating as plain text.")
            # History already updated, just return text
            return {"text": llm_text}

    except Exception as e:
        logger.error(f"Unexpected error processing LLM response: {e}", exc_info=True)
        return {"error": f"Unexpected error processing response: {e}"}


def process_user_message(user_message: str) -> Optional[Dict[str, Any]]:
    """
    Processes a single user message using the LLM and tools.
    Manages conversation history persistence.
    """
    logger.info(f"Processing user message: {user_message[:100]}...")

    # 1. Prepare context (loads/updates/saves history, formats for LLM)
    context = _prepare_context(user_message)
    if not context and user_message:
        logger.error(
            "Failed to prepare context, possibly due to history formatting error."
        )
        return {"error": "Context preparation failed."}
    elif not context:
        logger.warning("Empty user message received.")
        return {"warning": "Empty user message."}

    # 2. Prepare prompt/system instruction
    system_prompt = get_system_prompt(context)

    # No need to get tool definitions separately as they're now incorporated into the system prompt

    # 4. Call LLM
    response = llm_handler.call_llm_sync(
        contents=context,
        system_instruction=system_prompt,
        response_mime_type="application/json",
    )
    if not response:
        logger.error("LLM call failed. Response was None.")
        return {"error": "LLM call failed."}

    print(response)
    # 5. Process LLM response
    result = _process_llm_response(response)
    logger.info(f"Finished processing message. Result: {result}")
    return result


# Example Usage (for testing)
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("Starting message processor test.")

    # Clear history at start for clean test run
    _clear_history_cache()

    # Test 1: Simple message
    print("\n--- Test 1: Simple Message ---")
    result1 = process_user_message("Hello, how are you today?")
    print("Processing Result 1:", result1)
    print("Current History:", _conversation_history)

    # Test 2: Another message (builds on history)
    print("\n--- Test 2: Follow-up Message ---")
    result2 = process_user_message("What tools do you have available?")
    print("Processing Result 2:", result2)
    print("Current History:", _conversation_history)

    # Test 3: Message implying completion (should call 'finish' if LLM understands)
    # Note: This requires the LLM call to actually support and use tools.
    print("\n--- Test 3: Finish Message ---")
    result3 = process_user_message("Okay, that's all I needed, thank you!")
    print("Processing Result 3:", result3)
    print(
        "History after finish attempt:", _conversation_history
    )  # Should be empty if finish worked

    # Verify cache file deletion after finish
    print(
        f"Cache file exists after finish attempt: {os.path.exists(_HISTORY_CACHE_FILE)}"
    )

    logger.info("Message processor test finished.")
