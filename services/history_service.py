import logging
import json
import os
from typing import List

from .interfaces import IHistoryService, HistoryEntry

logger = logging.getLogger(__name__)

# Путь к файлу истории (можно вынести в конфигурацию при необходимости)
HISTORY_CACHE_FILE = "conversation_history.json"


class JsonFileHistoryService(IHistoryService):
    """
    Реализация сервиса истории, использующая JSON файл для хранения.
    """

    _history_cache: List[HistoryEntry]
    _is_loaded: bool = False

    def __init__(self, history_file_path: str = HISTORY_CACHE_FILE):
        """
        Инициализирует сервис. Загрузка происходит лениво при первом доступе
        или принудительно через вызов load().
        """
        self._history_file_path = history_file_path
        self._history_cache = []
        self._is_loaded = False  # Загрузка произойдет при первом get/append/clear
        logger.debug(f"HistoryService initialized with file: {self._history_file_path}")

    def load(self) -> None:
        """Загружает историю из JSON файла, если она еще не загружена."""
        if self._is_loaded:
            return

        logger.debug(f"Attempting to load history from {self._history_file_path}")
        if not os.path.exists(self._history_file_path):
            logger.info(
                f"History cache file not found at {self._history_file_path}. Starting fresh."
            )
            self._history_cache = []
            self._is_loaded = True
            return

        try:
            with open(self._history_file_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)
            # Простая валидация формата
            if isinstance(history_data, list):
                self._history_cache = history_data
                logger.info(
                    f"Loaded {len(self._history_cache)} entries from history cache: {self._history_file_path}"
                )
            else:
                logger.warning(
                    f"History cache file {self._history_file_path} has invalid format (not a list). Starting fresh."
                )
                self._history_cache = []
        except json.JSONDecodeError:
            logger.error(
                f"Error decoding history cache file {self._history_file_path}. Starting fresh.",
                exc_info=True,
            )
            self._history_cache = []
        except Exception as e:
            logger.error(
                f"Error loading history cache file {self._history_file_path}: {e}. Starting fresh.",
                exc_info=True,
            )
            self._history_cache = []
        finally:
            self._is_loaded = True

    def _save(self) -> None:
        """Сохраняет текущее состояние истории в JSON файл."""
        logger.debug(f"Attempting to save history to {self._history_file_path}")
        try:
            dir_name = os.path.dirname(self._history_file_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            with open(self._history_file_path, "w", encoding="utf-8") as f:
                json.dump(self._history_cache, f, indent=2, ensure_ascii=False)
            logger.debug(
                f"Saved {len(self._history_cache)} entries to history cache: {self._history_file_path}"
            )
        except Exception as e:
            logger.error(
                f"Error saving history cache file {self._history_file_path}: {e}",
                exc_info=True,
            )

    def get_history(self) -> List[HistoryEntry]:
        """Возвращает текущую историю диалога, загружая ее при необходимости."""
        if not self._is_loaded:
            self.load()
        return self._history_cache

    def append_entry(self, entry: HistoryEntry) -> None:
        """Добавляет запись в историю и сохраняет ее."""
        if not self._is_loaded:
            self.load()
        self._history_cache.append(entry)
        logger.debug(f"Appended entry. History size: {len(self._history_cache)}")
        self._save()

    def clear_history(self) -> None:
        """Очищает историю диалога и сохраняет пустое состояние."""
        logger.info(f"Clearing history cache and file: {self._history_file_path}")
        self._history_cache = []
        self._is_loaded = True  # Считаем загруженной (пустой)
        self._save()

    def set_history(self, history: List[HistoryEntry]) -> None:
        """Полностью перезаписывает текущую историю."""
        logger.warning(f"Overwriting history cache with {len(history)} entries.")
        self._history_cache = history
        self._is_loaded = True
        self._save()
