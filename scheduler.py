import logging
from datetime import datetime, timedelta, time
from typing import Optional, List
import todoist_handler
import config
from utils import is_working_time

logger = logging.getLogger(__name__)

DEFAULT_DURATION_MINUTES = 30


def _format_response_message(
    created_task, due_string, project_id, priority, language="ru"
):
    """Formats response message in the appropriate language with better context."""
    if not created_task:
        return (
            "❌ Не удалось создать задачу в Todoist."
            if language == "ru"
            else "❌ Failed to create task in Todoist."
        )

    final_due = due_string if due_string else "без срока"
    if created_task.due:
        final_due = created_task.due.string

    project_name = "Входящие" if language == "ru" else "Inbox"
    if project_id and project_id != "inbox":
        projects = todoist_handler.get_projects()
        for p in projects:
            if p["id"] == project_id:
                project_name = p["name"]
                break

    priority_text = {
        "ru": {1: "высший", 2: "высокий", 3: "средний", 4: "низкий"},
        "en": {1: "highest", 2: "high", 3: "medium", 4: "low"},
    }

    if language == "ru":
        return f"✅ Задача '{created_task.content}' добавлена в проект '{project_name}' со сроком '{final_due}' (Приоритет: {priority_text['ru'][priority]})."
    else:
        return f"✅ Task '{created_task.content}' added to '{project_name}' project with deadline '{final_due}' (Priority: {priority_text['en'][priority]})."


def schedule_task(task_details: dict, source: str) -> tuple[bool, str]:
    """
    Attempts to schedule a task based on LLM-provided details.
    Returns (success: bool, message_for_user: str).
    """
    # Detect language from the action text (simple heuristic)
    action = task_details.get("action", "")
    language = (
        "ru"
        if any(char in action for char in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
        else "en"
    )

    details = task_details.get("details", "")
    priority = task_details.get("priority", 4)
    duration_minutes = task_details.get("estimated_duration_minutes")
    project_id = task_details.get("project_id")
    deadline_str = task_details.get("deadline")

    logger.debug(
        f"Task details - Action: {action}, Duration: {duration_minutes} min, Deadline: {deadline_str}"
    )

    if not action:
        msg = (
            "Не удалось определить суть задачи. Попробуйте переформулировать."
            if language == "ru"
            else "Could not extract task essence. Try rephrasing."
        )
        logger.error(f"Scheduler: Failed to schedule task - missing 'action'.")
        return False, msg

    # Initialize scheduling variables
    now = datetime.now()
    schedule_in_slot = True  # Default to slot-based scheduling
    start_time = now + timedelta(
        minutes=15 - now.minute % 15
    )  # Round to next 15 minutes
    duration = timedelta(
        minutes=(
            duration_minutes
            if duration_minutes is not None
            else DEFAULT_DURATION_MINUTES
        )
    )

    # Handle scheduling logic
    if deadline_str:
        try:
            if len(deadline_str) > 10:  # Has time component
                target_time = datetime.fromisoformat(deadline_str)
            else:  # Only date
                target_time = datetime.fromisoformat(deadline_str + " 00:00")

            # If it's a future date, use work start hour
            if target_time.date() > now.date():
                target_time = datetime.combine(
                    target_time.date(), time(config.WORK_START_HOUR)
                )

            # Use target time as the start time
            start_time = target_time
            schedule_in_slot = True
        except ValueError:
            logger.warning(
                f"Invalid deadline format: {deadline_str}, using current time"
            )
            start_time = now + timedelta(minutes=15 - now.minute % 15)

    # Find a suitable slot if needed
    if schedule_in_slot:
        end_search = start_time + timedelta(days=7)
        enforce_working_hours = source in ["slack", "jira"]

        existing_tasks_raw = todoist_handler.get_tasks(start_time, end_search)
        existing_slots = []
        for task in existing_tasks_raw:
            if task.due and task.due.datetime:
                try:
                    task_start = datetime.fromisoformat(
                        task.due.datetime.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    task_end = task_start + duration  # Use actual task duration
                    existing_slots.append((task_start, task_end))
                except ValueError:
                    logger.warning(f"Could not process task time {task.id}")

        existing_slots.sort()
        found_slot = find_free_slot(
            start_time,
            end_search,
            duration,
            existing_slots,
            enforce_working_hours,
            config.WORK_DAYS,
            config.WORK_START_HOUR,
            config.WORK_END_HOUR,
        )

        if found_slot:
            due_string = found_slot.strftime("%Y-%m-%d %H:%M")
            logger.info(
                f"Scheduler: Found slot for '{action}' at {due_string} (duration: {duration_minutes} min)"
            )
        else:
            due_string = start_time.strftime("%Y-%m-%d %H:%M")
            logger.warning(f"Scheduler: Using start time {due_string} as fallback")
    else:
        due_string = start_time.strftime("%Y-%m-%d %H:%M")

    # Format the task content and description to include duration
    task_content = action

    # Include duration in content and description
    if duration_minutes:
        duration_str_ru = f"({duration_minutes} мин)"
        duration_str_en = f"({duration_minutes} min)"

        # Add duration to task name in brackets
        task_content = (
            f"{action} {duration_str_ru if language == 'ru' else duration_str_en}"
        )

        # Add detailed duration to description
        duration_text = ""
        if duration_minutes >= 60:
            hours = duration_minutes // 60
            mins = duration_minutes % 60
            if language == "ru":
                duration_text = f"Продолжительность: {hours} ч"
                if mins > 0:
                    duration_text += f" {mins} мин"
            else:
                duration_text = f"Duration: {hours} hr"
                if mins > 0:
                    duration_text += f" {mins} min"
        else:
            duration_text = (
                f"Продолжительность: {duration_minutes} мин"
                if language == "ru"
                else f"Duration: {duration_minutes} min"
            )

        details = f"{duration_text}\n{details}"

    # Create the task with proper duration in both content and description
    created_task = todoist_handler.create_task(
        content=action,  # Using the original action name without duration suffix
        description=details.strip() if details else None,
        project_id=project_id,
        priority=priority,
        due_string=due_string,
        duration_minutes=duration_minutes,  # Pass duration directly to Todoist API
    )

    return bool(created_task), _format_response_message(
        created_task, due_string, project_id, priority, language
    )


def find_free_slot(
    start_search: datetime,
    end_search: datetime,
    duration: timedelta,
    existing_slots: list[tuple[datetime, datetime]],
    enforce_working_hours: bool,
    work_days: list[int],
    start_hour: int,
    end_hour: int,
) -> Optional[datetime]:
    """Finds first free slot of given duration."""

    current_time = start_search
    current_time = current_time + timedelta(minutes=15 - current_time.minute % 15)

    while current_time < end_search:
        potential_end_time = current_time + duration

        if enforce_working_hours:
            if not (
                is_working_time(current_time, work_days, start_hour, end_hour)
                and is_working_time(
                    potential_end_time - timedelta(minutes=1),
                    work_days,
                    start_hour,
                    end_hour,
                )
            ):
                current_time = _get_next_working_start(
                    current_time, work_days, start_hour
                )
                if current_time >= end_search:
                    break
                continue

        is_free = True
        for task_start, task_end in existing_slots:
            if (current_time < task_end) and (task_start < potential_end_time):
                is_free = False
                current_time = task_end + timedelta(minutes=1)
                current_time = current_time + timedelta(
                    minutes=15 - current_time.minute % 15
                )
                break

        if is_free:
            logger.debug(
                f"Found free slot: {current_time.strftime('%Y-%m-%d %H:%M')} - {potential_end_time.strftime('%H:%M')}"
            )
            return current_time

    logger.debug("No free slot found in given range.")
    return None


def _get_next_working_start(
    current_time: datetime, work_days: list[int], start_hour: int
) -> datetime:
    """Finds start of next working interval."""
    if (
        current_time.isoweekday() in work_days
        and current_time.hour >= config.WORK_END_HOUR
    ):
        next_day = current_time.date() + timedelta(days=1)
    else:
        next_day = current_time.date()

    while next_day.isoweekday() not in work_days:
        next_day += timedelta(days=1)

    return datetime.combine(next_day, time(start_hour))
