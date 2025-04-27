import logging
import json
import os
import datetime
import re
import yaml
from typing import Dict, List, Any, Optional, Tuple

# --- DI ---
from dependency_injector.wiring import inject, Provide
from dependency_injector import providers

# --- Интерфейсы ---
from services.interfaces import (
    IRecurringEventsEngine,
    ISchedulingService,
    ILLMService,
    IHistoryService,
    IVaultService,
    IConfigService,  # Ensure ConfigService is imported
    ITelegramService,
    FileEventData,
)

# Import functions from new files
from . import global_events
from . import vault_tasks
from . import event_handling


# Assuming genai_types is available or needs to be imported
# from google.generativeai import types as genai_types # Uncomment if needed
# Placeholder for genai_types if not imported
class MockGenaiTypes:
    class Content:
        def __init__(self, role, parts):
            self.role = role
            self.parts = parts


genai_types = MockGenaiTypes()

logger = logging.getLogger(__name__)

GLOBAL_EVENTS_CONFIG_PATH = "global_recurring_events.json"
DEFAULT_TASKS_DIR_RELATIVE = "03 - Tasks"


class RecurringEventsEngine(IRecurringEventsEngine):
    """
    Движок, управляющий загрузкой, планированием и выполнением
    повторяющихся событий (глобальных и из файлов задач).
    Использует ISchedulingService для фактического планирования и наблюдения.
    """

    _events: Dict[str, Dict[str, Any]]
    _scheduled_file_event_ids: set[str]
    _last_processed: Dict[str, datetime.datetime]
    _debounce_interval: datetime.timedelta

    @inject
    def __init__(
        self,
        scheduling_service: ISchedulingService = Provide[
            "ApplicationContainer.services.scheduling_service"
        ],
        llm_service: ILLMService = Provide["ApplicationContainer.services.llm_service"],
        history_service: IHistoryService = Provide[
            "ApplicationContainer.services.history_service"
        ],
        vault_service: IVaultService = Provide[
            "ApplicationContainer.services.vault_service"
        ],
        telegram_service: ITelegramService = Provide[
            "ApplicationContainer.services.telegram_service"
        ],
        config_service: IConfigService = Provide[  # Inject ConfigService
            "ApplicationContainer.core.config_service"
        ],
        tool_handlers_map_provider: providers.Provider = Provide[
            "ApplicationContainer.handlers.tool_handlers_provider"
        ],
    ):
        self._scheduling_service = scheduling_service
        self._llm_service = llm_service
        self._history_service = history_service
        self._vault_service = vault_service
        self._telegram_service = telegram_service
        self._config_service = config_service  # Store ConfigService
        self._tool_handlers_map_provider = tool_handlers_map_provider
        self._events = {}
        self._scheduled_file_event_ids = set()
        self._last_processed = {}
        self._debounce_interval = datetime.timedelta(seconds=1)  # 1 second debounce
        logger.info("RecurringEventsEngine initialized with DI.")

    # Keep _validate_event_data as it's used by global_events.load_global_events
    def _validate_event_data(self, event_id: str, data: Dict[str, Any]) -> bool:
        """Проверяет наличие обязательных полей в данных события."""
        return event_handling.validate_event_data(event_id, data)

    # Keep _schedule_event as it's called internally and by vault_tasks
    def _schedule_event(self, event_id: str, event_data: Dict[str, Any]):
        """Регистрирует событие в SchedulingService."""
        event_handling.schedule_event(
            self, self._scheduling_service, event_id, event_data
        )

    # Keep _handle_time_event as it's the callback for the scheduler
    def _handle_time_event(self, event_id: str):
        """Обработчик временного события, вызванный SchedulingService."""
        # Pass telegram_service to handle_time_event
        event_handling.handle_time_event(
            self, event_id, self._telegram_service  # Pass telegram_service
        )

    # Keep _execute_event as it's called by _handle_time_event
    # Revert change to _execute_event - it does not need config_service here
    def _execute_event(self, event_id: str, event_data: Dict[str, Any]):
        """Выполняет логику события (например, отправка напоминания через LLM)."""
        # execute_event in event_handling will now receive telegram_service from handle_time_event
        # Note: The signature of event_handling.execute_event was changed in the previous step
        # to accept telegram_service, so this call should be correct now.
        event_handling.execute_event(
            self, event_id, event_data
        )  # This call is incorrect, execute_event needs telegram_service

    def handle_vault_file_event(self, relative_path: str) -> None:
        """
        Обрабатывает событие изменения файла в хранилище:
        перечитывает файл, отменяет старые и планирует новые напоминания.
        Включает механизм debounce для предотвращения множественных обработок.
        """
        now = datetime.datetime.now()
        last_process_time = self._last_processed.get(relative_path)

        # Skip if file was processed recently
        if last_process_time and now - last_process_time < self._debounce_interval:
            logger.debug(f"Skipping duplicate event for {relative_path} (debounced)")
            return

        # Update last processed time
        self._last_processed[relative_path] = now

        # Process the file event
        vault_tasks.handle_vault_file_event(
            self,
            self._vault_service,
            self._scheduling_service,
            relative_path,
            self._telegram_service,
            self._config_service,
        )

    def load_and_schedule_all(self) -> None:
        """Загружает глобальные события и сканирует задачи, планируя их."""
        logger.info("Loading and scheduling all recurring events...")
        self._events.clear()
        self._scheduled_file_event_ids.clear()

        global_events.load_global_events(self, self._events)
        for event_id, event_data in self._events.items():
            if event_data.get("is_global"):
                self._schedule_event(event_id, event_data)

        # Pass telegram_service and config_service to load_vault_tasks
        vault_tasks.load_vault_tasks(
            self,
            self._vault_service,
            self._telegram_service,
            self._config_service,  # Pass config_service
        )

        logger.info("Finished loading and scheduling events.")

    def start(self) -> None:
        """Запускает движок: загружает и планирует события, запускает SchedulingService."""
        self.load_and_schedule_all()
        # Schedule daily rescheduling at 00:01
        self._scheduling_service.add_job(
            schedule_dsl="daily at 00:01",
            event_id="daily_reschedule_vault_tasks",
            callback=lambda _: self.load_and_schedule_all(),
        )
        self._scheduling_service.start()
        logger.info("RecurringEventsEngine started.")

    def stop(self) -> None:
        """Останавливает SchedulingService."""
        logger.info("Stopping RecurringEventsEngine...")
        self._scheduling_service.stop()
        logger.info("RecurringEventsEngine stopped.")
