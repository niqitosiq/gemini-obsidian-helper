import logging
import os

from typing import Optional, Union, List, Dict, Any, Sequence

# Import the specific config variables needed
from config import GEMINI_API_KEY, GEMINI_MODEL_NAME

import google.genai as genai
from google.genai import types
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

_client: Optional[genai.Client] = None
# Use the configured model name
_model_name = GEMINI_MODEL_NAME

try:
    # Use the imported variable directly
    if not GEMINI_API_KEY:
        # The warning/error is now handled in config/__init__.py
        # We just check if it's None here to prevent client initialization
        logger.warning(
            "Gemini client not initialized because GEMINI_API_KEY is missing."
        )
        _client = None
    else:
        # Use the imported variable directly
        _client = genai.Client(api_key=GEMINI_API_KEY)
        # Update log message to use the configured model name
        logger.info(f"Gemini API client configured for model '{_model_name}'.")
except Exception as e:
    logger.critical(f"Critical error configuring Gemini API: {e}", exc_info=True)
    _client = None


# --- Generic Synchronous LLM Call ---
def call_llm_sync(
    contents: List[Union[str, types.Part, types.Content]],
    system_instruction: Optional[str] = None,
    response_mime_type: Optional[str] = None,
    max_output_tokens: Optional[int] = 20000,
) -> Optional[types.GenerateContentResponse]:
    """Generic synchronous call to the Gemini API."""

    print(
        contents,
        system_instruction,
    )
    if not _client:
        logger.error("LLM call impossible: Gemini client not initialized.")
        return None

    # Prepare config parameters
    config_params = {}
    if system_instruction:
        config_params["system_instruction"] = system_instruction
    if response_mime_type:
        # Note: response_mime_type is part of GenerateContentConfig in docs
        config_params["response_mime_type"] = response_mime_type
    if max_output_tokens:
        config_params["max_output_tokens"] = max_output_tokens
    else:
        logger.debug("Calling LLM sync without tools.")

    generation_config = (
        types.GenerateContentConfig(**config_params) if config_params else None
    )

    # Prepare arguments for generate_content
    generate_content_args = {
        "model": _model_name,
        "contents": contents,
    }
    # Add config only if it's not None
    if generation_config:
        generate_content_args["config"] = generation_config  # Use 'config' key

    try:
        logger.debug(
            f"Calling LLM sync. Model: {_model_name}. Args: {generate_content_args}. Contents start: {str(contents)[:200]}..."
        )
        # Pass the arguments directly to generate_content
        response = _client.models.generate_content(**generate_content_args)
        logger.debug(
            f"LLM sync call successful. Response text start: {getattr(response, 'text', 'N/A')[:100]}..."
        )
        return response
    except genai_errors.APIError as e:
        logger.error(f"Gemini API error during sync call: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during sync LLM call: {e}", exc_info=True)
        return None


# --- Generic Asynchronous LLM Call ---
async def call_llm_async(  # Renamed to be public
    contents: List[Union[str, types.Part, types.Content]],
    system_instruction: Optional[str] = None,
    response_mime_type: Optional[str] = None,
    max_output_tokens: Optional[int] = 20000,
) -> Optional[types.GenerateContentResponse]:
    """Generic asynchronous call to the Gemini API."""
    if not _client:
        logger.error("LLM async call impossible: Gemini client not initialized.")
        return None

    # Prepare config parameters
    config_params = {}
    if system_instruction:
        config_params["system_instruction"] = system_instruction
    if response_mime_type:
        config_params["response_mime_type"] = response_mime_type
    if max_output_tokens:
        config_params["max_output_tokens"] = max_output_tokens

    generation_config = (
        types.GenerateContentConfig(**config_params) if config_params else None
    )

    # Prepare arguments for generate_content
    generate_content_args = {
        "model": _model_name,
        "contents": contents,
    }
    # Add config only if it's not None
    if generation_config:
        generate_content_args["config"] = generation_config  # Use 'config' key

    try:
        logger.debug(
            f"Calling LLM async. Model: {_model_name}. Args: {generate_content_args}. Contents start: {str(contents)[:200]}..."
        )
        # Pass the arguments directly to generate_content
        response = await _client.aio.models.generate_content(**generate_content_args)
        logger.debug(
            f"LLM async call successful. Response text start: {getattr(response, 'text', 'N/A')[:100]}..."
        )
        return response
    except genai_errors.APIError as e:
        logger.error(f"Gemini API error during async call: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during async LLM call: {e}", exc_info=True)
        return None


# --- NEW: Add function to upload file (needed for transcription) ---
def upload_file(file_path: str) -> Optional[types.File]:
    """Uploads a file to the Gemini service."""
    if not _client:
        logger.error("File upload impossible: Gemini client not initialized.")
        return None
    try:
        logger.info(f"Uploading file: {file_path}")
        if not os.path.exists(file_path):
            logger.error(f"File for upload not found: {file_path}")
            return None

        uploaded_file = _client.files.upload(file=file_path)
        logger.info(f"File uploaded successfully: {uploaded_file.name}")
        return uploaded_file
    except genai_errors.APIError as e:
        logger.error(f"Gemini API error during file upload: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during file upload: {e}", exc_info=True)
        return None


# --- NEW: Add function to delete file (needed for transcription) ---
def delete_file(file_name: str) -> bool:
    """Deletes a file from the Gemini service."""
    if not _client:
        logger.error("File deletion impossible: Gemini client not initialized.")
        return False
    try:
        logger.info(f"Deleting file: {file_name}")
        _client.files.delete(name=file_name)
        logger.info(f"File deleted successfully: {file_name}")
        return True
    except genai_errors.APIError as e:
        # Handle cases where the file might already be deleted or doesn't exist
        if isinstance(e, genai_errors.NotFoundError):
            logger.warning(
                f"File not found for deletion (might be already deleted): {file_name}"
            )
            return True  # Treat as success if not found
        logger.error(f"Gemini API error during file deletion: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error during file deletion: {e}", exc_info=True)
        return False


# --- NEW: Function to transcribe audio using generic components ---
def transcribe_audio_file(audio_file_path: str) -> Optional[str]:
    """
    Transcribes an audio file using the Gemini API.

    Orchestrates file upload, transcription call, and file deletion.
    """
    uploaded_file_object: Optional[types.File] = None
    try:
        # 1. Upload file
        uploaded_file_object = upload_file(audio_file_path)
        if not uploaded_file_object:
            logger.error(
                f"Transcription failed: Could not upload file {audio_file_path}"
            )
            return None

        # 2. Call LLM for transcription
        prompt = "Transcribe this audio file verbatim."
        # The 'contents' for transcription includes the prompt and the file object
        contents_for_api = [prompt, uploaded_file_object]

        logger.info(f"Requesting transcription for file: {uploaded_file_object.name}")
        response = call_llm_sync(contents=contents_for_api)  # Use the generic sync call

        if not response or not response.text:
            logger.error(
                f"Transcription failed: No response text from LLM for file {uploaded_file_object.name}"
            )
            return None

        transcribed_text = response.text.strip()
        logger.info(
            f"Audio successfully transcribed (length: {len(transcribed_text)}): {transcribed_text[:100]}..."
        )
        return transcribed_text

    except Exception as e:
        logger.error(
            f"Unexpected error during transcription process for {audio_file_path}: {e}",
            exc_info=True,
        )
        return None
    finally:
        # 3. Delete file from server
        if uploaded_file_object and hasattr(uploaded_file_object, "name"):
            deleted = delete_file(uploaded_file_object.name)
            if not deleted:
                logger.warning(
                    f"Failed to delete uploaded file {uploaded_file_object.name} from server."
                )
