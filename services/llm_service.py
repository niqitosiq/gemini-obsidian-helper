import logging
import os
from typing import Optional, Union, List, Dict, Any, Sequence
import asyncio
import time

import google.genai as genai

# Removed direct import of GenerativeModel
from google.genai import types as genai_types
from google.genai import errors as genai_errors

from .interfaces import ILLMService, IConfigService

logger = logging.getLogger(__name__)

# Значение по умолчанию для max_output_tokens, если не передано
DEFAULT_MAX_OUTPUT_TOKENS = 20000

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 10  # seconds

class LLMServiceImpl(ILLMService):
    """Реализация сервиса для взаимодействия с Gemini API."""

    _client: Optional[genai.Client]
    # Removed _model attribute
    _model_name: str

    def __init__(self, config_service: IConfigService):
        self._config_service = config_service
        self._client = None
        self._model_name = "unknown"  # Инициализируем значением по умолчанию
        self._initialize_client()

    def _initialize_client(self):
        """Инициализирует клиент Gemini API при создании сервиса."""
        if self._client is not None:
            logger.warning("LLM client already initialized for this service instance.")
            return

        api_key = self._config_service.get_gemini_api_key()
        # Получаем имя модели, используем значение из config или fallback
        self._model_name = self._config_service.get_gemini_model_name()

        if not api_key:
            logger.error(
                "Gemini client cannot be initialized because GEMINI_API_KEY is missing in config."
            )
            self._client = None
            return

        try:
            self._client = genai.Client(api_key=api_key)
            # Removed model initialization
            logger.info(
                f"LLMService initialized. Gemini API client configured for model '{self._model_name}'."
            )
        except Exception as e:
            logger.critical(
                f"Critical error configuring Gemini API client: {e}", exc_info=True
            )
            self._client = None

    async def _async_retry_with_exponential_backoff(self, func, *args, **kwargs):
        """Helper method to implement retry logic with exponential backoff for async functions."""
        retry_count = 0
        delay = INITIAL_RETRY_DELAY

        while retry_count < MAX_RETRIES:
            try:
                return await func(*args, **kwargs)
            except genai_errors.APIError as e:
                retry_count += 1
                if retry_count == MAX_RETRIES:
                    logger.error(f"Failed after {MAX_RETRIES} retries: {e}", exc_info=True)
                    return None
                
                logger.warning(
                    f"API error on attempt {retry_count}/{MAX_RETRIES}, retrying in {delay}s: {e}"
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RETRY_DELAY)  # Exponential backoff with cap

        return None

    def _sync_retry_with_exponential_backoff(self, func, *args, **kwargs):
        """Helper method to implement retry logic with exponential backoff for sync functions."""
        retry_count = 0
        delay = INITIAL_RETRY_DELAY

        while retry_count < MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except genai_errors.APIError as e:
                retry_count += 1
                if retry_count == MAX_RETRIES:
                    logger.error(f"Failed after {MAX_RETRIES} retries: {e}", exc_info=True)
                    return None
                
                logger.warning(
                    f"API error on attempt {retry_count}/{MAX_RETRIES}, retrying in {delay}s: {e}"
                )
                time.sleep(delay)
                delay = min(delay * 2, MAX_RETRY_DELAY)  # Exponential backoff with cap

        return None

    async def call_async(
        self,
        contents: List[Union[str, genai_types.Part, genai_types.Content]],
        system_instruction: Optional[str] = None,
        response_mime_type: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Optional[genai_types.GenerateContentResponse]:
        """Асинхронный вызов LLM."""
        if not self._client or not self._client.aio:
            logger.error(
                "LLM async call impossible: Gemini client (or aio) not initialized."
            )
            return None

        effective_max_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else DEFAULT_MAX_OUTPUT_TOKENS
        )

        config_params = {}
        if system_instruction:
            config_params["system_instruction"] = system_instruction
        if response_mime_type:
            config_params["response_mime_type"] = response_mime_type
        if effective_max_tokens is not None:
            config_params["max_output_tokens"] = effective_max_tokens

        generation_config_obj = (
            genai_types.GenerateContentConfig(**config_params)
            if config_params
            else None
        )

        generate_content_args = {
            "model": self._model_name,
            "contents": contents,
        }
        if generation_config_obj:
            generate_content_args["config"] = generation_config_obj

        try:
            logger.debug(
                f"Calling LLM async. Model: {self._model_name}. Args keys: {list(generate_content_args.keys())}. Contents start: {str(contents)[:200]}..."
            )
            
            async def _generate_content():
                return await self._client.aio.models.generate_content(**generate_content_args)
            
            response = await self._async_retry_with_exponential_backoff(_generate_content)
            
            if response:
                logger.debug(
                    f"LLM async call successful. Response text start: {getattr(response, 'text', 'N/A')[:100]}..."
                )
            return response
            
        except Exception as e:
            logger.error(f"Unexpected error during async LLM call: {e}", exc_info=True)
            return None

    def call_sync(
        self,
        contents: List[Union[str, genai_types.Part, genai_types.Content]],
        system_instruction: Optional[str] = None,
        response_mime_type: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Optional[genai_types.GenerateContentResponse]:
        """Синхронный вызов LLM."""
        if not self._client:
            logger.error("LLM sync call impossible: Gemini client not initialized.")
            return None

        effective_max_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else DEFAULT_MAX_OUTPUT_TOKENS
        )

        config_params = {}
        if system_instruction:
            config_params["system_instruction"] = system_instruction
        if response_mime_type:
            config_params["response_mime_type"] = response_mime_type
        if effective_max_tokens is not None:
            config_params["max_output_tokens"] = effective_max_tokens

        generation_config_obj = (
            genai_types.GenerateContentConfig(**config_params)
            if config_params
            else None
        )

        generate_content_args = {
            "model": self._model_name,
            "contents": contents,
        }
        if generation_config_obj:
            generate_content_args["config"] = generation_config_obj

        try:
            logger.debug(
                f"Calling LLM sync. Model: {self._model_name}. Args keys: {list(generate_content_args.keys())}. Contents start: {str(contents)[:200]}..."
            )
            
            def _generate_content():
                return self._client.models.generate_content(**generate_content_args)
            
            response = self._sync_retry_with_exponential_backoff(_generate_content)
            
            if response:
                logger.debug(
                    f"LLM sync call successful. Response text start: {getattr(response, 'text', 'N/A')[:100]}..."
                )
            return response
            
        except Exception as e:
            logger.error(f"Unexpected error during sync LLM call: {e}", exc_info=True)
            return None

    def upload_file(self, file_path: str) -> Optional[genai_types.File]:
        """Загружает файл для использования с API."""
        if not self._client:
            logger.error("File upload impossible: Gemini client not initialized.")
            return None
        try:
            logger.info(f"Uploading file via LLMService: {file_path}")
            if not os.path.exists(file_path):
                logger.error(f"File for upload not found: {file_path}")
                return None

            uploaded_file = self._client.files.upload(file=file_path)
            logger.info(f"File uploaded successfully: {uploaded_file.name}")
            return uploaded_file
        except genai_errors.APIError as e:
            logger.error(f"Gemini API error during file upload: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {e}", exc_info=True)
            return None

    def delete_file(self, file_name: str) -> bool:
        """Удаляет файл, загруженный ранее."""
        if not self._client:
            logger.error("File deletion impossible: Gemini client not initialized.")
            return False
        try:
            logger.info(f"Deleting file via LLMService: {file_name}")
            self._client.files.delete(name=file_name)
            logger.info(f"File deleted successfully: {file_name}")
            return True
        except genai_errors.APIError as e:
            if isinstance(e, genai_errors.NotFoundError):
                logger.warning(
                    f"File not found for deletion (might be already deleted): {file_name}"
                )
                return True
            logger.error(f"Gemini API error during file deletion: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error during file deletion: {e}", exc_info=True)
            return False

    def transcribe_audio(self, audio_file_path: str) -> Optional[str]:
        """Оркестрирует загрузку, транскрипцию и удаление аудиофайла."""
        uploaded_file_object: Optional[genai_types.File] = None
        try:
            # 1. Upload file using self method
            uploaded_file_object = self.upload_file(audio_file_path)
            if not uploaded_file_object:
                logger.error(
                    f"Transcription failed: Could not upload file {audio_file_path}"
                )
                return None

            # 2. Call LLM for transcription using self method
            prompt = "Transcribe this audio file verbatim."
            contents_for_api = [prompt, uploaded_file_object]

            logger.info(
                f"Requesting transcription for file: {uploaded_file_object.name}"
            )
            response = self.call_sync(
                contents=contents_for_api
            )  # Вызываем синхронный метод сервиса

            if not response or not hasattr(response, "text") or not response.text:
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
            # 3. Delete file from server using self method
            if uploaded_file_object and hasattr(uploaded_file_object, "name"):
                deleted = self.delete_file(uploaded_file_object.name)
                if not deleted:
                    logger.warning(
                        f"Failed to delete uploaded file {uploaded_file_object.name} from server."
                    )
