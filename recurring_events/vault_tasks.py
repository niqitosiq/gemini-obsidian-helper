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
) -> Optional[Tuple[datetime.datetime, str, str, Optional[str], Optional[List[str]], Optional[str]]]:
    """Извлекает и валидирует детали задачи из frontmatter, включая рекуррентность."""
    task_date_str = frontmatter_data.get("date")
    task_time_str = frontmatter_data.get(
        "startTime"
    )  # Expecting HH:MM string from parse_frontmatter
    task_title = frontmatter_data.get("title", os.path.basename(relative_path))
    task_completed = frontmatter_data.get("completed", False)
    task_status = frontmatter_data.get("status", None)
    task_type = frontmatter_data.get("type")
    days_of_week = frontmatter_data.get("daysOfWeek")
    start_recur_str = frontmatter_data.get("startRecur")

    # Treat as active if not completed, regardless of status field
    if (
        not task_date_str
        or not task_time_str
        or task_completed is True
        or (task_status is not None and task_status != "todo")
    ):
        logger.debug(
            f"Skipping scheduling for {relative_path}: missing date/time, completed: {task_completed}, status: {task_status}"
        )
        return None

    try:
        # Combine date and time and parse, expecting HH:MM format for time
        task_datetime_str = f"{task_date_str} {task_time_str}"
        task_datetime = datetime.datetime.strptime(task_datetime_str, "%Y-%m-%d %H:%M")

        now = datetime.datetime.now()

        # Validate recurrence fields if present
        start_recur_date = None
        if task_type == "recurring":
            if not days_of_week or not isinstance(days_of_week, list):
                logger.warning(f"Recurring task '{relative_path}' missing or invalid 'daysOfWeek'. Skipping.")
                return None
            if start_recur_str:
                try:
                    if isinstance(start_recur_str, datetime.date):
                        start_recur_date = start_recur_str
                    elif isinstance(start_recur_str, str):
                        start_recur_date = datetime.datetime.strptime(start_recur_str, "%Y-%m-%d").date()
                    else:
                        logger.warning(f"Recurring task '{relative_path}' has unrecognized type for 'startRecur': {type(start_recur_str)}. Skipping.")
                        return None

                    # If startRecur is in the future, don't schedule yet
                    if start_recur_date > now.date():
                         logger.debug(f"Recurring task '{relative_path}' start date {start_recur_date} is in the future. Skipping for now.")
                         return None
                except ValueError: # Catch parsing errors specifically
                    logger.warning(f"Recurring task '{relative_path}' has invalid 'startRecur' date format: {start_recur_str}. Skipping.")
                    return None
                except Exception as e: # Catch other potential errors
                    logger.error(f"Error processing 'startRecur' for {relative_path}: {e}", exc_info=True)
                    return None
            # For recurring tasks, we don't skip based on the initial task_datetime being in the past
            # The scheduling service will handle the weekly trigger.
        elif task_datetime < now: # Check for non-recurring tasks being in the past
            logger.debug(f"Task in {relative_path} is in the past. Skipping reminders.")
            return None

        return task_datetime, task_title, task_time_str, task_type, days_of_week, start_recur_str

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
                task_datetime, task_title, task_time_str, task_type, days_of_week, start_recur_str = task_details
                schedule_task = False
                schedule_dsl_prefix = "daily at" # Default for non-recurring

                if task_type == "recurring":
                    # Map daysOfWeek: M, T, W, R, F, S, U
                    day_map = {'M': 'monday', 'T': 'tuesday', 'W': 'wednesday', 'R': 'thursday', 'F': 'friday', 'S': 'saturday', 'U': 'sunday'}
                    valid_days = [day_map[d] for d in days_of_week if d in day_map]
                    if not valid_days:
                        logger.warning(f"Recurring task '{relative_path}' has no valid days in 'daysOfWeek': {days_of_week}. Skipping.")
                        continue

                    # Construct DSL: "every monday and thursday at"
                    schedule_dsl_prefix = f"every {' and '.join(valid_days)} at"
                    schedule_task = True # Always schedule recurring tasks if start date is valid
                else:
                    # Non-recurring: Check if date is today
                    task_date_str = frontmatter_data.get("date")
                    if task_date_str:
                        try:
                            if isinstance(task_date_str, datetime.date):
                                task_date = task_date_str
                            elif isinstance(task_date_str, str):
                                task_date = datetime.datetime.strptime(task_date_str, "%Y-%m-%d").date()
                            else:
                                logger.warning(f"Unrecognized type for task date '{task_date_str}' in {relative_path}: {type(task_date_str)}")
                                continue

                            if task_date == datetime.date.today():
                                schedule_task = True
                        except Exception as e:
                            logger.warning(f"Could not parse task date '{task_date_str}' in {relative_path}: {e}")
                            continue
                    else:
                        logger.warning(f"Non-recurring task '{relative_path}' missing date. Skipping.")
                        continue

                if schedule_task:
                    reminder_30m_time, reminder_5m_time = calculate_reminder_times(
                        task_datetime
                    )

                    if reminder_30m_time:
                        event_id_30m = f"reminder_30m_{relative_path}"
                        prompt_30m = f"Remind user about: Task '{task_title}' is starting in 30 minutes ({task_time_str})."
                        schedule_dsl_30m = f"{schedule_dsl_prefix} {reminder_30m_time.strftime('%H:%M')}"
                        event_data_30m = {
                            "schedule_time": schedule_dsl_30m,
                            "prompt": prompt_30m,
                            "is_file_event": True,
                            "user_id": user_id,
                        }
                        engine._events[event_id_30m] = event_data_30m
                        engine._schedule_event(event_id_30m, event_data_30m)
                        engine._scheduled_file_event_ids.add(event_id_30m)
                        logger.info(
                            f"Scheduled 30m reminder for '{task_title}' ({relative_path}) with rule: {schedule_dsl_30m}"
                        )

                    if reminder_5m_time:
                        event_id_5m = f"reminder_5m_{relative_path}"
                        prompt_5m = f"Remind user about: Task '{task_title}' is starting in 5 minutes ({task_time_str})."
                        schedule_dsl_5m = f"{schedule_dsl_prefix} {reminder_5m_time.strftime('%H:%M')}"
                        event_data_5m = {
                            "schedule_time": schedule_dsl_5m,
                            "prompt": prompt_5m,
                            "is_file_event": True,
                            "user_id": user_id,
                        }
                        engine._events[event_id_5m] = event_data_5m
                        engine._schedule_event(event_id_5m, event_data_5m)
                        engine._scheduled_file_event_ids.add(event_id_5m)
                        logger.info(
                            f"Scheduled 5m reminder for '{task_title}' ({relative_path}) with rule: {schedule_dsl_5m}"
                        )

        except Exception as e:
            logger.error(
                f"Error processing task file {relative_path}: {e}",
                exc_info=True,
            )


# (Duplicating the logic from load_vault_tasks for handling file events)
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
            task_datetime, task_title, task_time_str, task_type, days_of_week, start_recur_str = task_details
            schedule_task = False
            schedule_dsl_prefix = "daily at" # Default for non-recurring

            if task_type == "recurring":
                # Map daysOfWeek: M, T, W, R, F, S, U
                day_map = {'M': 'monday', 'T': 'tuesday', 'W': 'wednesday', 'R': 'thursday', 'F': 'friday', 'S': 'saturday', 'U': 'sunday'}
                valid_days = [day_map[d] for d in days_of_week if d in day_map]
                if not valid_days:
                    logger.warning(f"Recurring task '{relative_path}' has no valid days in 'daysOfWeek': {days_of_week}. Skipping.")
                    return # Use return instead of continue in handle_vault_file_event

                # Construct DSL: "every monday and thursday at"
                schedule_dsl_prefix = f"every {' and '.join(valid_days)} at"
                schedule_task = True # Always schedule recurring tasks if start date is valid
            else:
                # Non-recurring: Check if date is today
                task_date_str = frontmatter_data.get("date")
                if task_date_str:
                    try:
                        if isinstance(task_date_str, datetime.date):
                            task_date = task_date_str
                        elif isinstance(task_date_str, str):
                            task_date = datetime.datetime.strptime(task_date_str, "%Y-%m-%d").date()
                        else:
                            logger.warning(f"Unrecognized type for task date '{task_date_str}' in {relative_path}: {type(task_date_str)}")
                            return # Use return

                        if task_date == datetime.date.today():
                            schedule_task = True
                    except Exception as e:
                        logger.warning(f"Could not parse task date '{task_date_str}' in {relative_path}: {e}")
                        return # Use return
                else:
                    logger.warning(f"Non-recurring task '{relative_path}' missing date. Skipping.")
                    return # Use return

            if schedule_task:
                reminder_30m_time, reminder_5m_time = calculate_reminder_times(
                    task_datetime
                )

                if reminder_30m_time:
                    prompt_30m = f"Remind user about: Task '{task_title}' is starting in 30 minutes ({task_time_str})."
                    schedule_dsl_30m = f"{schedule_dsl_prefix} {reminder_30m_time.strftime('%H:%M')}"
                    event_data_30m = {
                        "schedule_time": schedule_dsl_30m,
                        "prompt": prompt_30m,
                        "is_file_event": True,
                        "user_id": user_id,
                    }
                    engine._events[event_id_30m] = event_data_30m
                    engine._schedule_event(
                        event_id_30m,
                        event_data_30m,
                    )
                    engine._scheduled_file_event_ids.add(event_id_30m)
                    logger.info(
                        f"Scheduled 30m reminder for '{task_title}' ({relative_path}) with rule: {schedule_dsl_30m}"
                    )

                if reminder_5m_time:
                    prompt_5m = f"Remind user about: Task '{task_title}' is starting in 5 minutes ({task_time_str})."
                    schedule_dsl_5m = f"{schedule_dsl_prefix} {reminder_5m_time.strftime('%H:%M')}"
                    event_data_5m = {
                        "schedule_time": schedule_dsl_5m,
                        "prompt": prompt_5m,
                        "is_file_event": True,
                        "user_id": user_id,
                    }
                    engine._events[event_id_5m] = event_data_5m
                    engine._schedule_event(
                        event_id_5m,
                        event_data_5m,
                    )
                    engine._scheduled_file_event_ids.add(event_id_5m)
                    logger.info(
                        f"Scheduled 5m reminder for '{task_title}' ({relative_path}) with rule: {schedule_dsl_5m}"
                    )

    except Exception as e:
        logger.error(
            f"Error processing task file {relative_path} during event handling: {e}",
            exc_info=True,
        )
