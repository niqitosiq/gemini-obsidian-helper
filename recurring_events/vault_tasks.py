import logging
import os
import datetime
import re
import yaml
from typing import Dict, List, Any, Optional, Tuple

# --- Интерфейсы ---
from services.interfaces import (
    IRecurringEventsEngine,
    ISchedulingService,
    IVaultService,
    FileEventData,
    ITelegramService,
    IConfigService,  # Import IConfigService
)

logger = logging.getLogger(__name__)
# TODO: If this bot is single-user, consider fetching the primary user ID from config.
# PRIMARY_USER_ID = None # Example: config_service.get_primary_user_id()

DEFAULT_TASKS_DIR_RELATIVE = "03 - Tasks"


def parse_frontmatter(content: str) -> Dict[str, Any]:
    """Парсит YAML frontmatter из содержимого файла."""
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if frontmatter_match:
        frontmatter_content = frontmatter_match.group(1)
        try:
            data = yaml.safe_load(frontmatter_content) or {}
            # Convert integer startTime/endTime to HH:MM strings if they exist
            # Also handle string times like "8:30" or "14:00" and ensure HH:MM format
            for key in ["startTime", "endTime"]:
                time_value = data.get(key)
                if isinstance(time_value, (int, float)):
                    try:
                        minutes = int(time_value)
                        data[key] = f"{minutes // 60:02d}:{minutes % 60:02d}"
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Could not convert {key} number to integer: {time_value}"
                        )
                        data[key] = None  # Set to None if conversion fails
                elif isinstance(time_value, str):
                    time_value = time_value.strip()
                    # Attempt to parse and reformat string times to ensure HH:MM
                    try:
                        # Try parsing common formats
                        if ":" in time_value:
                            parts = time_value.split(":")
                            if len(parts) == 2:
                                hours = int(parts[0])
                                minutes = int(parts[1])
                                if 0 <= hours <= 23 and 0 <= minutes <= 59:
                                    data[key] = f"{hours:02d}:{minutes:02d}"
                                else:
                                    logger.warning(
                                        f"Invalid time value for {key}: {time_value}"
                                    )
                                    data[key] = None
                            else:
                                logger.warning(
                                    f"Unexpected time string format for {key}: {time_value}"
                                )
                                data[key] = None
                        elif len(time_value) == 4 and time_value.isdigit():
                            # Handle 4-digit integer strings like "0830" or "1400"
                            hours = int(time_value[:2])
                            minutes = int(time_value[2:])
                            if 0 <= hours <= 23 and 0 <= minutes <= 59:
                                data[key] = f"{hours:02d}:{minutes:02d}"
                            else:
                                logger.warning(
                                    f"Invalid 4-digit time value for {key}: {time_value}"
                                )
                                data[key] = None
                        else:
                            logger.warning(
                                f"Unrecognized time string format for {key}: {time_value}"
                            )
                            data[key] = None

                    except (ValueError, TypeError):
                        logger.warning(
                            f"Could not parse or reformat {key} string: {time_value}"
                        )
                        data[key] = None  # Set to None if parsing fails
                elif time_value is not None:
                    logger.warning(f"Unexpected type for {key}: {type(time_value)}")
                    data[key] = None  # Set to None for unexpected types

            return data
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse YAML frontmatter: {e}")
            return {}
    return {}


def extract_and_validate_task_details(
    frontmatter_data: Dict[str, Any], relative_path: str
) -> Optional[Tuple[datetime.datetime, str, str]]:
    """Извлекает и валидирует детали задачи из frontmatter."""
    task_date_str = frontmatter_data.get("date")
    task_time_str = frontmatter_data.get(
        "startTime"
    )  # Expecting HH:MM string from parse_frontmatter
    task_title = frontmatter_data.get("title", os.path.basename(relative_path))
    task_completed = frontmatter_data.get("completed", False)
    task_status = frontmatter_data.get("status", "unknown")

    # Remove debug logs
    # logger.warning(
    #     f"DEBUG: raw_time_value: {raw_time_value}, type: {type(raw_time_value)}"
    # )
    # logger.warning(
    #     f"DEBUG: task_time_str: {task_time_str}, type: {type(task_time_str)}"
    # )

    if (
        not task_date_str
        or not task_time_str
        or task_completed
        or task_status != "todo"
    ):
        logger.debug(
            f"Skipping scheduling for {relative_path}: missing date/time, completed, or not a todo."
        )
        return None

    try:
        # Combine date and time and parse, expecting HH:MM format for time
        task_datetime_str = f"{task_date_str} {task_time_str}"
        task_datetime = datetime.datetime.strptime(task_datetime_str, "%Y-%m-%d %H:%M")

        now = datetime.datetime.now()
        if task_datetime < now:
            logger.debug(f"Task in {relative_path} is in the past. Skipping reminders.")
            return None

        return task_datetime, task_title, task_time_str

    except ValueError as e:
        logger.warning(f"Could not parse date or time for task in {relative_path}: {e}")
        return None
    except Exception as e:
        logger.error(
            f"Error extracting task details from {relative_path}: {e}",
            exc_info=True,
        )
        return None


def calculate_reminder_times(
    task_datetime: datetime.datetime,
) -> Tuple[Optional[datetime.datetime], Optional[datetime.datetime]]:
    """Рассчитывает время напоминаний (за 30 и 5 минут)."""
    now = datetime.datetime.now()
    reminder_30m_time = task_datetime - datetime.timedelta(minutes=30)
    reminder_5m_time = task_datetime - datetime.timedelta(minutes=5)

    return (
        reminder_30m_time if reminder_30m_time > now else None,
        reminder_5m_time if reminder_5m_time > now else None,
    )


def load_vault_tasks(
    engine: IRecurringEventsEngine,
    vault_service: IVaultService,
    telegram_service: ITelegramService,
    config_service: IConfigService,  # Add config_service parameter
) -> None:
    """
    Сканирует файлы задач в хранилище, парсит их и планирует напоминания.
    """
    user_id = (
        telegram_service.get_current_user_id()
    )  # Attempt to get user ID from TelegramService

    if user_id is None:
        logger.warning(
            "Could not determine user_id from TelegramService during task load. "
            "Attempting to use primary user ID from config as fallback."
        )
        configured_ids = config_service.get_telegram_user_ids()
        if configured_ids:
            user_id = int(
                configured_ids[0]
            )  # Use the first ID as primary, convert to int
            logger.info(f"Using primary user ID from config: {user_id}")
        else:
            logger.error(
                "No user_id from TelegramService and no primary user ID found in config. "
                "Cannot schedule reminders with a target user."
            )
            # Keep user_id as None, subsequent logic should handle this

    logger.debug(f"Loading tasks from vault (resolved user_id: {user_id})...")
    vault_root = vault_service.get_vault_root()
    if not vault_root:
        logger.error("Vault root not configured, cannot load vault tasks.")
        return

    tasks_dir = os.path.join(vault_root, DEFAULT_TASKS_DIR_RELATIVE)
    if not os.path.isdir(tasks_dir):
        logger.info(
            f"Tasks directory not found: {tasks_dir}. Skipping vault task loading."
        )
        return

    markdown_files = vault_service.read_all_markdown_files()
    logger.info(
        f"Read {len(markdown_files)} markdown files from vault for task processing."
    )

    for relative_path, content in markdown_files.items():
        frontmatter_data = parse_frontmatter(content)

        if not relative_path.startswith(DEFAULT_TASKS_DIR_RELATIVE + os.sep):
            continue

        logger.debug(f"Processing vault file for tasks: {relative_path}")
        try:
            task_details = extract_and_validate_task_details(
                frontmatter_data, relative_path
            )

            if task_details:
                task_datetime, task_title, task_time_str = task_details
                reminder_30m_time, reminder_5m_time = calculate_reminder_times(
                    task_datetime
                )

                if reminder_30m_time:
                    event_id_30m = f"reminder_30m_{relative_path}"
                    prompt_30m = f"Reminder: Task '{task_title}' is starting in 30 minutes ({task_time_str} today)."
                    schedule_dsl_30m = f"daily at {reminder_30m_time.strftime('%H:%M')}"
                    event_data_30m = {
                        "schedule_time": schedule_dsl_30m,
                        "prompt": prompt_30m,
                        "is_file_event": True,
                        "user_id": user_id,  # Re-add user_id to event_data
                    }
                    engine._events[event_id_30m] = event_data_30m
                    engine._schedule_event(event_id_30m, event_data_30m)
                    engine._scheduled_file_event_ids.add(event_id_30m)
                    logger.info(
                        f"Scheduled 30m reminder for '{task_title}' ({relative_path}) at {reminder_30m_time.strftime('%H:%M')}"
                    )

                if reminder_5m_time:
                    event_id_5m = f"reminder_5m_{relative_path}"
                    prompt_5m = f"Reminder: Task '{task_title}' is starting in 5 minutes ({task_time_str} today)."
                    schedule_dsl_5m = f"daily at {reminder_5m_time.strftime('%H:%M')}"
                    event_data_5m = {
                        "schedule_time": schedule_dsl_5m,
                        "prompt": prompt_5m,
                        "is_file_event": True,
                        "user_id": user_id,  # Re-add user_id to event_data
                    }
                    engine._events[event_id_5m] = event_data_5m  # Add to engine._events
                    engine._schedule_event(event_id_5m, event_data_5m)
                    engine._scheduled_file_event_ids.add(event_id_5m)
                    logger.info(
                        f"Scheduled 5m reminder for '{task_title}' ({relative_path}) at {reminder_5m_time.strftime('%H:%M')}"
                    )

        except Exception as e:
            logger.error(
                f"Error processing task file {relative_path}: {e}",
                exc_info=True,
            )


def handle_vault_file_event(
    engine: IRecurringEventsEngine,
    vault_service: IVaultService,
    scheduling_service: ISchedulingService,
    relative_path: str,
    telegram_service: ITelegramService,
    config_service: IConfigService,  # Add config_service parameter
) -> None:
    """
    Обрабатывает событие изменения файла в хранилище:
    перечитывает файл, отменяет старые и планирует новые напоминания.
    """
    user_id = (
        telegram_service.get_current_user_id()
    )  # Attempt to get user ID from TelegramService

    if user_id is None:
        logger.warning(
            f"Could not determine user_id from TelegramService during file event for {relative_path}. "
            "Attempting to use primary user ID from config as fallback."
        )
        configured_ids = config_service.get_telegram_user_ids()
        if configured_ids:
            user_id = int(
                configured_ids[0]
            )  # Use the first ID as primary, convert to int
            logger.info(f"Using primary user ID from config: {user_id}")
        else:
            logger.error(
                f"No user_id from TelegramService and no primary user ID found in config for file event {relative_path}. "
                "Cannot update reminders with a target user."
            )
            # Keep user_id as None, subsequent logic should handle this

    logger.info(
        f"Handling vault file event for: {relative_path} (resolved user_id: {user_id})"
    )

    if not relative_path.startswith(DEFAULT_TASKS_DIR_RELATIVE + os.sep):
        logger.debug(f"File {relative_path} is not in the tasks directory. Skipping.")
        return

    safe_path = vault_service.resolve_path(relative_path)
    if not safe_path:
        logger.error(f"Cannot handle file event due to unsafe path: {relative_path}")
        return

    event_id_30m = f"reminder_30m_{relative_path}"
    event_id_5m = f"reminder_5m_{relative_path}"
    scheduling_service.unschedule(event_id_30m)
    scheduling_service.unschedule(event_id_5m)
    logger.debug(f"Unschedled existing reminders for {relative_path}")

    if not vault_service.file_exists(relative_path):
        logger.info(f"File {relative_path} deleted. Reminders unscheduled.")
        return

    content = vault_service.read_file(relative_path)
    if content is None:
        logger.error(
            f"Could not read file content for {relative_path}. Cannot reschedule reminders."
        )
        return

    frontmatter_data = parse_frontmatter(content)

    try:
        task_details = extract_and_validate_task_details(
            frontmatter_data, relative_path
        )

        if task_details:
            task_datetime, task_title, task_time_str = task_details
            reminder_30m_time, reminder_5m_time = calculate_reminder_times(
                task_datetime
            )

            if reminder_30m_time:
                prompt_30m = f"Reminder: Task '{task_title}' is starting in 30 minutes ({task_time_str} today)."
                schedule_dsl_30m = f"daily at {reminder_30m_time.strftime('%H:%M')}"
                event_data_30m = {
                    "schedule_time": schedule_dsl_30m,
                    "prompt": prompt_30m,
                    "is_file_event": True,
                    "user_id": user_id,  # Re-add user_id to event_data
                }
                engine._events[event_id_30m] = event_data_30m
                engine._schedule_event(
                    event_id_30m,
                    event_data_30m,
                )
                engine._scheduled_file_event_ids.add(event_id_30m)
                logger.info(
                    f"Scheduled 30m reminder for '{task_title}' ({relative_path}) at {reminder_30m_time.strftime('%H:%M')}"
                )

            if reminder_5m_time:
                prompt_5m = f"Reminder: Task '{task_title}' is starting in 5 minutes ({task_time_str} today)."
                schedule_dsl_5m = f"daily at {reminder_5m_time.strftime('%H:%M')}"

                event_data_5m = {
                    "schedule_time": schedule_dsl_5m,
                    "prompt": prompt_5m,
                    "is_file_event": True,
                    "user_id": user_id,  # Re-add user_id to event_data
                }
                engine._events[event_id_5m] = event_data_5m  # Add to engine._eventsents
                engine._schedule_event(
                    event_id_5m,
                    event_data_5m,
                )
                engine._scheduled_file_event_ids.add(event_id_5m)
                logger.info(
                    f"Scheduled 5m reminder for '{task_title}' ({relative_path}) at {reminder_5m_time.strftime('%H:%M')}"
                )

    except Exception as e:
        logger.error(
            f"Error processing task file {relative_path} during event handling: {e}",
            exc_info=True,
        )
