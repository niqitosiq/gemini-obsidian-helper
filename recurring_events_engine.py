import logging
import json
import os
import datetime
import re
from typing import Dict, List, Any, Optional

# --- DI ---
from dependency_injector.wiring import inject, Provide
from dependency_injector import providers  # Import providers for type hinting

# from containers import ApplicationContainer # Removed to break circular import

# --- Интерфейсы ---
from services.interfaces import (
    IRecurringEventsEngine,
    ISchedulingService,
    ILLMService,
    IHistoryService,
    IVaultService,
    IConfigService,
    FileEventData,
)

logger = logging.getLogger(__name__)

# Путь к файлу глобальных событий (можно вынести в конфиг)
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

    @inject
    def __init__(
        self,
        # Use string paths for Provide to avoid circular import
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
        config_service: IConfigService = Provide[
            "ApplicationContainer.core.config_service"
        ],
        # Add the missing tool handlers map provider
        tool_handlers_map_provider: providers.Dict = Provide[
            "ApplicationContainer.handlers.tool_handlers_provider"
        ],
    ):
        self._scheduling_service = scheduling_service
        self._llm_service = llm_service
        self._history_service = history_service
        self._vault_service = vault_service
        self._config_service = config_service
        self._tool_handlers_map_provider = (
            tool_handlers_map_provider  # Store the provider
        )
        self._events = {}
        self._scheduled_file_event_ids = set()
        logger.info("RecurringEventsEngine initialized with DI.")

    def _load_global_events(self) -> None:
        """Загружает глобальные события из JSON файла."""
        logger.debug(f"Loading global events from {GLOBAL_EVENTS_CONFIG_PATH}")
        try:
            if os.path.exists(GLOBAL_EVENTS_CONFIG_PATH):
                with open(GLOBAL_EVENTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                    global_events = json.load(f)
                logger.info(f"Loaded {len(global_events)} global recurring events")
                for event_id, event_data in global_events.items():
                    if self._validate_event_data(event_id, event_data):
                        event_data["is_global"] = True
                        self._events[event_id] = event_data
                    else:
                        logger.error(
                            f"Invalid event data structure for global event '{event_id}'. Skipping."
                        )
            else:
                logger.info(
                    f"Global events file not found: {GLOBAL_EVENTS_CONFIG_PATH}. No global events loaded."
                )
        except Exception as e:
            logger.error(f"Error loading global recurring events: {e}", exc_info=True)

    def _validate_event_data(self, event_id: str, data: Dict[str, Any]) -> bool:
        """Проверяет наличие обязательных полей в данных события."""
        required_keys = ["schedule_time", "prompt"]
        if not all(key in data for key in required_keys):
            logger.error(
                f"Event '{event_id}' data is missing required keys: {required_keys}. Data: {data}"
            )
            return False
        return True

    def _schedule_event(self, event_id: str, event_data: Dict[str, Any]):
        """Регистрирует событие в SchedulingService."""
        schedule_dsl = event_data.get("schedule_time")
        if not schedule_dsl:
            logger.error(
                f"Cannot schedule event '{event_id}': missing 'schedule_time'."
            )
            return

        success = self._scheduling_service.add_job(
            schedule_dsl=schedule_dsl,
            event_id=event_id,
            callback=self._handle_time_event,
        )
        if success:
            logger.info(
                f"Successfully scheduled event '{event_id}' with rule: {schedule_dsl}"
            )
        else:
            logger.error(
                f"Failed to schedule event '{event_id}' with rule: {schedule_dsl}"
            )

    def _handle_time_event(self, event_id: str):
        """Обработчик временного события, вызванный SchedulingService."""
        logger.info(f"Handling scheduled time event: {event_id}")
        event_data = self._events.get(event_id)
        if not event_data:
            logger.error(f"Event data not found for triggered event ID: {event_id}")
            return

        self._execute_event(event_id, event_data)
        event_data["last_run"] = datetime.datetime.now().isoformat()

    def _execute_event(self, event_id: str, event_data: Dict[str, Any]):
        """Выполняет логику события (например, отправка напоминания через LLM)."""
        logger.info(f"Executing logic for event: {event_id}")
        prompt_template = event_data.get(
            "prompt", "Scheduled event occurred: {event_id}"
        )

        try:
            current_datetime = datetime.datetime.now()
            formatted_prompt = prompt_template.format(
                event_id=event_id,
                date=current_datetime.strftime("%Y-%m-%d"),
                time=current_datetime.strftime("%H:%M"),
            )

            logger.debug(
                f"Formatted prompt for event '{event_id}': {formatted_prompt[:100]}..."
            )

            current_history = self._history_service.get_history()
            llm_contents = [
                genai_types.Content(
                    role=entry["role"],
                    parts=[p["text"] for p in entry["parts"] if "text" in p],
                )
                for entry in current_history
                if entry.get("parts")
            ]
            llm_contents.append(
                genai_types.Content(role="user", parts=[formatted_prompt])
            )

            response = self._llm_service.call_sync(
                contents=llm_contents, response_mime_type="application/json"
            )

            if not response:
                logger.error(f"LLM call failed for event '{event_id}'.")
                return

            llm_text_response = ""
            if hasattr(response, "text") and response.text:
                llm_text_response = response.text
            elif (
                response.parts
                and hasattr(response.parts[0], "text")
                and response.parts[0].text
            ):
                llm_text_response = response.parts[0].text

            if not llm_text_response:
                logger.warning(f"LLM returned empty response for event '{event_id}'.")
                return

            logger.debug(
                f"LLM raw response for event '{event_id}': {llm_text_response[:100]}..."
            )
            self._history_service.append_entry(
                {"role": "model", "parts": [{"text": llm_text_response}]}
            )

        except Exception as e:
            logger.error(f"Error executing event '{event_id}': {e}", exc_info=True)

    def load_and_schedule_all(self) -> None:
        """Загружает глобальные события и сканирует задачи, планируя их."""
        logger.info("Loading and scheduling all recurring events...")
        self._events.clear()
        self._scheduled_file_event_ids.clear()
        self._load_global_events()
        for event_id, event_data in self._events.items():
            if event_data.get("is_global"):
                self._schedule_event(event_id, event_data)
        logger.info("Finished loading and scheduling events.")

    def start(self) -> None:
        """Запускает движок: загружает и планирует события, запускает SchedulingService."""
        self.load_and_schedule_all()
        self._scheduling_service.start()
        logger.info("RecurringEventsEngine started.")

    def stop(self) -> None:
        """Останавливает SchedulingService."""
        logger.info("Stopping RecurringEventsEngine...")
        self._scheduling_service.stop()
        logger.info("RecurringEventsEngine stopped.")
