from typing import (
    Protocol,
    Optional,
    List,
    Dict,
    Any,
    Union,
    Sequence,
    TypedDict,
    Callable,
)
from google.genai import types as genai_types
import datetime

# Импортируем типы Telegram для интерфейса
from telegram import Update
from telegram.ext import ContextTypes

# --- Определение структуры записи истории ---
# Используем TypedDict для лучшей ясности структуры
# from typing import TypedDict # Уже импортирован выше


class HistoryEntryPart(
    TypedDict, total=False
):  # total=False означает, что ключи не обязательны
    text: Optional[str]
    # Могут быть другие типы частей, например, для function_call/response
    # function_call: Optional[Any]
    # function_response: Optional[Any]


class HistoryEntry(TypedDict):
    role: str  # 'user' или 'model'
    parts: List[HistoryEntryPart]


# --- Интерфейс Сервиса Конфигурации (без изменений) ---
class IConfigService(Protocol):
    """Интерфейс для доступа к конфигурационным параметрам приложения."""

    def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]: ...
    def get_str(self, key: str, default: Optional[str] = None) -> Optional[str]: ...
    def get_list_str(
        self, key: str, default: Optional[List[str]] = None
    ) -> Optional[List[str]]: ...
    def get_gemini_api_key(self) -> Optional[str]: ...
    def get_gemini_model_name(self) -> str: ...
    def get_telegram_bot_token(self) -> Optional[str]: ...
    def get_telegram_user_ids(self) -> List[str]: ...
    def get_obsidian_vault_path(self) -> Optional[str]: ...
    def get_obsidian_daily_notes_folder(self) -> Optional[str]: ...


# --- Интерфейс Сервиса LLM (НОВОЕ) ---
class ILLMService(Protocol):
    """Интерфейс для взаимодействия с LLM (например, Gemini)."""

    async def call_async(
        self,
        contents: List[Union[str, genai_types.Part, genai_types.Content]],
        system_instruction: Optional[str] = None,
        response_mime_type: Optional[str] = None,
        max_output_tokens: Optional[int] = None,  # Убрано значение по умолчанию
    ) -> Optional[genai_types.GenerateContentResponse]:
        """Асинхронный вызов LLM."""
        ...

    def call_sync(
        self,
        contents: List[Union[str, genai_types.Part, genai_types.Content]],
        system_instruction: Optional[str] = None,
        response_mime_type: Optional[str] = None,
        max_output_tokens: Optional[int] = None,  # Убрано значение по умолчанию
    ) -> Optional[genai_types.GenerateContentResponse]:
        """Синхронный вызов LLM."""
        ...

    def upload_file(self, file_path: str) -> Optional[genai_types.File]:
        """Загружает файл для использования с API."""
        ...

    def delete_file(self, file_name: str) -> bool:
        """Удаляет файл, загруженный ранее."""
        ...

    def transcribe_audio(self, audio_file_path: str) -> Optional[str]:
        """
        Оркестрирует загрузку, транскрипцию и удаление аудиофайла.
        Возвращает транскрибированный текст или None в случае ошибки.
        """
        ...


# --- Интерфейс Сервиса Vault (НОВОЕ) ---
class IVaultService(Protocol):
    """Интерфейс для взаимодействия с файловой системой Obsidian Vault."""

    def get_vault_root(self) -> Optional[str]:
        """Возвращает абсолютный путь к корню Obsidian Vault."""
        ...

    def resolve_path(self, relative_path: str) -> Optional[str]:
        """
        Преобразует относительный путь внутри хранилища в безопасный абсолютный путь.
        Возвращает None, если путь небезопасен или выходит за пределы хранилища.
        """
        ...

    def create_file(self, relative_path: str, content: str) -> bool:
        """Создает или перезаписывает файл по относительному пути с указанным содержимым."""
        ...

    def modify_file(self, relative_path: str, content: str) -> bool:
        """Перезаписывает существующий файл по относительному пути."""
        ...

    def delete_file(self, relative_path: str) -> bool:
        """Удаляет файл по относительному пути."""
        ...

    def create_folder(self, relative_path: str) -> bool:
        """Создает папку по относительному пути (включая родительские)."""
        ...

    def delete_folder(self, relative_path: str) -> bool:
        """Удаляет папку по относительному пути (рекурсивно)."""
        ...

    def read_file(self, relative_path: str) -> Optional[str]:
        """Читает содержимое файла по относительному пути."""
        ...

    def file_exists(self, relative_path: str) -> bool:
        """Проверяет существование файла по относительному пути."""
        ...

    def folder_exists(self, relative_path: str) -> bool:
        """Проверяет существование папки по относительному пути."""
        ...

    def list_files(self, relative_path: str = ".") -> Optional[List[str]]:
        """Возвращает список файлов и папок в указанной относительной директории."""
        ...

    def read_all_markdown_files(self) -> Dict[str, str]:
        """
        Рекурсивно читает все markdown файлы (.md) в хранилище.
        Возвращает словарь, где ключ - относительный путь файла от корня хранилища,
        а значение - содержимое файла.
        """
        ...


# --- Интерфейс Сервиса Истории ---
class IHistoryService(Protocol):
    """Интерфейс для управления историей диалогов."""

    def load(self) -> None:
        """Загружает историю из персистентного хранилища (если не загружена)."""
        ...

    def get_history(self) -> List[HistoryEntry]:
        """Возвращает текущую историю диалога."""
        ...

    def append_entry(self, entry: HistoryEntry) -> None:
        """Добавляет запись в историю и сохраняет ее."""
        ...

    def clear_history(self) -> None:
        """Очищает историю диалога и сохраняет пустое состояние."""
        ...

    def set_history(self, history: List[HistoryEntry]) -> None:
        """Полностью перезаписывает текущую историю (используется с осторожностью)."""
        ...


# --- Типы колбэков для планировщика ---
TimeEventCallback = Callable[[str], None]  # Принимает event_id
FileEventData = TypedDict(
    "FileEventData", {"event_type": str, "src_path": str, "is_directory": bool}
)
FileEventCallback = Callable[
    [FileEventData], None
]  # Принимает информацию о файловом событии


# --- Интерфейс Сервиса Планирования (НОВОЕ) ---
class ISchedulingService(Protocol):
    """Интерфейс для управления запланированными задачами и наблюдением за файлами."""

    def schedule_daily(
        self, time_str: str, event_id: str, callback: TimeEventCallback
    ) -> None:
        """Планирует ежедневное событие."""
        ...

    def schedule_weekly(
        self,
        weekday_str: str,
        time_str: str,
        event_id: str,
        callback: TimeEventCallback,
    ) -> None:
        """Планирует еженедельное событие."""
        ...

    def schedule_interval(
        self, interval: int, unit: str, event_id: str, callback: TimeEventCallback
    ) -> None:
        """Планирует событие с интервалом (minutes, hours, days)."""
        ...

    def add_job(
        self, schedule_dsl: str, event_id: str, callback: TimeEventCallback
    ) -> bool:
        """
        Добавляет задачу на основе строки описания расписания (например, "daily at 09:00", "every monday at 10:30").
        Возвращает True в случае успеха, False при ошибке парсинга.
        """
        ...

    def unschedule(self, event_id: str) -> None:
        """Отменяет запланированное событие по ID."""
        ...

    def watch_directory(self, path: str, callback: FileEventCallback) -> None:
        """Начинает наблюдение за директорией."""
        ...

    def start(self) -> None:
        """Запускает потоки планировщика и наблюдателя."""
        ...

    def stop(self) -> None:
        """Останавливает потоки планировщика и наблюдателя."""
        ...


# --- Интерфейс Движка Событий (уточнен) ---
class IRecurringEventsEngine(Protocol):
    """Интерфейс для управления движком повторяющихся событий."""

    def load_and_schedule_all(self) -> None:
        """Загружает глобальные события и сканирует задачи, планируя их."""
        ...

    def start(self) -> None:
        """Запускает движок и базовый сервис планирования."""
        ...

    def stop(self) -> None:
        """Останавливает движок и базовый сервис планирования."""
        ...

    def stop(self) -> None:
        """Останавливает движок и базовый сервис планирования."""
        ...


# --- Интерфейс Сервиса Построителя Промптов ---
class IPromptBuilderService(Protocol):
    """Интерфейс для построения промптов для LLM."""

    def build_system_prompt(
        self,
        current_history: List[HistoryEntry],
        vault_context: Optional[str] = None,
    ) -> str:
        """Конструирует системный промпт."""
        ...


# --- Интерфейс Сервиса Telegram (НОВОЕ) ---
class ITelegramService(Protocol):
    """Интерфейс для взаимодействия с Telegram из других частей системы (например, для отправки ответов)."""

    def set_current_context(
        self, update: Optional[Update], context: Optional[ContextTypes.DEFAULT_TYPE]
    ) -> None:
        """Устанавливает текущий контекст Update/Context для возможности отправки сообщений."""
        ...

    async def send_message(
        self, chat_id: int, text: str, parse_mode: Optional[str] = "Markdown"
    ) -> bool:
        """Отправляет сообщение в указанный чат."""
        ...

    async def send_message_to_user(
        self, user_id: int, text: str, parse_mode: Optional[str] = "Markdown"
    ) -> bool:
        """Отправляет сообщение указанному пользователю по его ID."""
        ...

    async def reply_to_current_message(
        self, text: str, parse_mode: Optional[str] = "Markdown"
    ) -> bool:
        """Отправляет сообщение в ответ на текущее обрабатываемое сообщение (если контекст установлен)."""
        ...


# --- Удаляем старые заглушки ---
