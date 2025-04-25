from dependency_injector import containers, providers
import logging

from config import load_app_config

# --- Интерфейсы ---
from services.interfaces import (
    IConfigService,
    ILLMService,
    IVaultService,
    IHistoryService,
    ISchedulingService,
    IRecurringEventsEngine,
    IPromptBuilderService,
    ITelegramService,
)

# --- Реализации Сервисов ---
from services.config_service import ConfigServiceImpl
from services.llm_service import LLMServiceImpl
from services.vault_service import VaultServiceImpl
from services.history_service import JsonFileHistoryService
from services.prompt_builder_service import PromptBuilderServiceImpl
from services.scheduling_service import SchedulingServiceImpl
from services.telegram_service import TelegramServiceImpl

# --- Движок Событий ---
from recurring_events import RecurringEventsEngine

# --- Обработчики Инструментов ---
from tools.tool_create_file import CreateFileToolHandler
from tools.tool_delete_file import DeleteFileToolHandler
from tools.tool_modify_file import ModifyFileToolHandler
from tools.tool_create_folder import CreateFolderToolHandler
from tools.tool_delete_folder import DeleteFolderToolHandler
from tools.tool_reply import ReplyToolHandler  # Обработчик Reply
from tools import finish as finish_tool_func  # Функция Finish

# --- Компоненты Telegram ---
# Removed direct import of TelegramMessageHandler to avoid potential issues
# from telegram_bot import TelegramMessageHandler
from telegram_bot import TelegramAppRunner, error_handler

# --- Модули для Wiring ---
# Imports removed - Wiring will be done in main.py to avoid circular imports
# import main
# import message_processor
# import telegram_bot
# import recurring_events as engine_module
# import tools.utils

# Можно добавить конкретные модули сервисов/обработчиков, если они используют @inject
# import services.vault_service
# import services.history_service
# import services.prompt_builder_service
# import services.scheduling_service
# import services.telegram_service
# import tools.tool_reply

logger = logging.getLogger(__name__)

# --- Контейнеры ---


class CoreContainer(containers.DeclarativeContainer):
    """Контейнер для базовых синглтонов и конфигурации."""

    config_dict = providers.Singleton(load_app_config)
    config_service = providers.Singleton(ConfigServiceImpl, config_data=config_dict)


class ServicesContainer(containers.DeclarativeContainer):
    """Контейнер для основных сервисов приложения."""

    core = providers.Container(CoreContainer)

    config_service = core.config_service  # Прокси для удобства

    llm_service: providers.Provider[ILLMService] = providers.Singleton(
        LLMServiceImpl, config_service=config_service
    )
    vault_service: providers.Provider[IVaultService] = providers.Singleton(
        VaultServiceImpl, config_service=config_service
    )
    history_service: providers.Provider[IHistoryService] = providers.Singleton(
        JsonFileHistoryService
        # Можно передать путь к файлу:
        # history_file_path=config_service.provided.get.call("HISTORY_FILE_PATH", "conversation_history.json")
    )
    prompt_builder_service: providers.Provider[IPromptBuilderService] = (
        providers.Singleton(PromptBuilderServiceImpl)
    )
    scheduling_service: providers.Provider[ISchedulingService] = providers.Singleton(
        SchedulingServiceImpl, config_service=config_service
    )
    telegram_service: providers.Provider[ITelegramService] = providers.Singleton(
        TelegramServiceImpl
    )


class HandlersContainer(containers.DeclarativeContainer):
    """Контейнер для обработчиков (инструментов, команд, запросов)."""

    core = providers.Container(CoreContainer)
    services = providers.Container(ServicesContainer, core=core)

    # --- Обработчики инструментов ---
    create_file_tool = providers.Factory(
        CreateFileToolHandler, vault_service=services.vault_service
    )
    delete_file_tool = providers.Factory(
        DeleteFileToolHandler, vault_service=services.vault_service
    )
    modify_file_tool = providers.Factory(
        ModifyFileToolHandler, vault_service=services.vault_service
    )
    create_folder_tool = providers.Factory(
        CreateFolderToolHandler, vault_service=services.vault_service
    )
    delete_folder_tool = providers.Factory(
        DeleteFolderToolHandler, vault_service=services.vault_service
    )
    reply_tool = providers.Factory(
        ReplyToolHandler, telegram_service=services.telegram_service
    )

    # --- Карта обработчиков/функций инструментов для message_processor ---
    tool_handlers_provider = providers.Dict(
        create_file=create_file_tool,
        delete_file=delete_file_tool,
        modify_file=modify_file_tool,
        create_folder=create_folder_tool,
        delete_folder=delete_folder_tool,
        reply=reply_tool,
        finish=providers.Object(finish_tool_func),
    )

    # --- Обработчики сообщений/команд/запросов ---
    # (Сам TelegramMessageHandler здесь, т.к. он обрабатывает входящие сообщения)
    # Using explicit constructor injection instead of @inject in the class
    telegram_message_handler = providers.Singleton(
        "telegram_bot.TelegramMessageHandler",  # Use string reference to avoid import
        llm_service=services.llm_service,
        telegram_service=services.telegram_service,
        history_service=services.history_service,
        vault_service=services.vault_service,  # Pass explicitly
        prompt_builder_service=services.prompt_builder_service,  # Pass explicitly
        tool_handlers_map_provider=tool_handlers_provider,  # Pass explicitly (Referencing provider within the same container)
    )

    # Можно добавить другие обработчики (CQRS) здесь
    # generate_llm_reply_query_handler = providers.Factory(...)
    # execute_tool_command_handler = providers.Factory(...)


class ApplicationContainer(containers.DeclarativeContainer):
    """Главный контейнер приложения, собирающий все компоненты."""

    core = providers.Container(CoreContainer)
    services = providers.Container(ServicesContainer, core=core)
    handlers = providers.Container(HandlersContainer, core=core, services=services)

    # --- Основные компоненты приложения ---
    recurring_events: providers.Provider[IRecurringEventsEngine] = providers.Singleton(
        RecurringEventsEngine,
        scheduling_service=services.scheduling_service,  # Keep one instance
        llm_service=services.llm_service,
        history_service=services.history_service,
        vault_service=services.vault_service,
        telegram_service=services.telegram_service,  # Add missing telegram_service dependency
        tool_handlers_map_provider=handlers.tool_handlers_provider,
    )

    telegram_app_runner = providers.Singleton(
        TelegramAppRunner,
        config_service=core.config_service,  # Add missing config_service dependency
        message_handler_instance=handlers.telegram_message_handler,
        # error_handler=providers.Object(error_handler) # Можно внедрить
    )

    logger.info("ApplicationContainer configured.")


# --- Функция для доступа к контейнеру ---
_app_container_instance = None


def get_container() -> ApplicationContainer:
    """Возвращает инициализированный инстанс главного DI контейнера."""
    global _app_container_instance
    if _app_container_instance is None:
        logger.info("Initializing DI container...")
        _app_container_instance = ApplicationContainer()
        # Wiring moved to main.py to avoid circular imports
        # modules_to_wire = [...]
        # unique_modules = list(dict.fromkeys(modules_to_wire))
        # _app_container_instance.wire(modules=unique_modules)
        logger.info("DI container initialized. Wiring should be done in main.py.")
    return _app_container_instance
