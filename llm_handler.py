# Этот файл больше не содержит основной логики взаимодействия с LLM.
# Эта логика перенесена в services/llm_service.py
# Файл можно удалить или оставить пустым, если нет вспомогательных
# функций, не вошедших в сервис.

# Убедимся, что он пуст или содержит только комментарии.
import logging

logger = logging.getLogger(__name__)
logger.debug("llm_handler.py is now deprecated. Use ILLMService via DI.")

# Функция initialize_llm_client() удалена, т.к. инициализация происходит в LLMServiceImpl.__init__

# Все остальные функции (call_llm_sync, call_llm_async, upload_file, delete_file, transcribe_audio_file) удалены.
