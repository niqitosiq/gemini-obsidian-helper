import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

# Add Update and ContextTypes imports
from telegram import Update
from telegram.ext import ContextTypes
import todoist_handler
import llm_handler
import config

# Import daily_scheduler for the command
from daily_scheduler import create_daily_schedule

logger = logging.getLogger(__name__)


# --- NEW Function to check command type without processing ---
async def check_semantic_command_type(message_text: str) -> Tuple[bool, Optional[str]]:
    """
    Quickly checks if a message matches known semantic command keywords
    and returns the command type if matched.
    Returns: (is_semantic, command_type)
    """
    message_lower = message_text.lower()
    schedule_keywords = [
        "запланируй",
        "распланируй",
        "создай расписание",
        "спланируй",
        "планируй",
        "план на день",
        "schedule day",
        "plan day",
    ]
    reschedule_keywords = ["перенеси", "отложи", "reschedule", "postpone"]

    if any(keyword in message_lower for keyword in schedule_keywords):
        return True, "schedule_day"
    if any(keyword in message_lower for keyword in reschedule_keywords):
        return True, "reschedule_tasks"

    # Add other command types here if needed

    return False, None


async def process_semantic_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str
) -> bool:
    """
    Process semantic commands for task management.
    Returns True if the message was processed as a semantic command.
    """
    chat_id = update.effective_chat.id
    is_semantic, command_type = await check_semantic_command_type(message_text)

    if not is_semantic:
        logger.debug(
            f"Message '{message_text}' not recognized as a semantic command by keywords."
        )
        return False

    # --- Handle different command types ---
    if command_type == "schedule_day":
        logger.info(f"Detected 'schedule_day' command via keyword: '{message_text}'")
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        # Pass context to create_daily_schedule
        # The calling function in telegram_bot already cleared skipped_in_session
        await create_daily_schedule(context.application, chat_id, context)
        return True

    elif command_type == "reschedule_tasks":
        logger.info(
            f"Detected 'reschedule_tasks' command via keyword: '{message_text}'"
        )
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        # Pass update and context to handle_task_rescheduling
        await handle_task_rescheduling(update, context, message_text)
        return True

    # --- Fallback/Unknown Semantic Command ---
    # If check_semantic_command_type returned True but no handler matched
    logger.warning(
        f"Semantic command type '{command_type}' detected but not handled for message: '{message_text}'"
    )
    return False  # Indicate it wasn't fully processed


async def handle_task_rescheduling(
    update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str
) -> None:
    """
    Use LLM to understand and execute task rescheduling requests.

    Examples:
    - "перенеси не важные задачи на завтра"
    - "перенеси задачу про гвозди на следующий вторник"
    - "перенеси всю стройку на три дня"
    """
    chat_id = update.effective_chat.id
    try:
        # First, notify the user that we're processing
        await context.bot.send_message(
            chat_id=chat_id, text="Анализирую запрос на перенос задач..."
        )

        # Use LLM to extract specific rescheduling parameters
        system_instruction = """Проанализируй запрос на перенос задач и извлеки следующие параметры:
1. `task_query`: Что именно нужно перенести (например, "не важные задачи", "задачу про гвозди", "всю стройку")
2. `target_date`: На какую дату перенести (в формате YYYY-MM-DD), либо укажи относительную дату ("tomorrow", "+3 days", "next Tuesday")
3. `is_low_priority_only`: Требуется ли переносить только низкоприоритетные задачи (true/false)
4. `search_by_project`: Требуется ли искать по проекту (true/false)
5. `project_name`: Название проекта, если применимо

Верни ответ строго в формате JSON.
"""

        # Use LLM to analyze the rescheduling request
        analysis = await get_rescheduling_parameters(message_text, system_instruction)

        if not analysis:
            await context.bot.send_message(
                chat_id=chat_id,
                text="К сожалению, не удалось разобрать запрос на перенос задач.",
            )
            return

        # Process the analyzed parameters
        task_query = analysis.get("task_query", "")
        target_date_str = analysis.get("target_date", "")
        is_low_priority = analysis.get("is_low_priority_only", False)
        search_by_project = analysis.get("search_by_project", False)
        project_name = analysis.get("project_name", "")

        # Convert relative date to absolute date
        target_date = await resolve_target_date(target_date_str)

        if not target_date:
            await context.bot.send_message(
                chat_id=chat_id, text="Не удалось определить дату для переноса задач."
            )
            return

        # Find and reschedule tasks
        tasks_moved, moved_tasks_info = await find_and_reschedule_tasks(
            task_query, target_date, is_low_priority, search_by_project, project_name
        )

        if not tasks_moved:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Не удалось найти задачи, соответствующие запросу '{task_query}'.",
            )
            return

        # Format and send success message
        weekday_names_ru = [
            "понедельник",
            "вторник",
            "среду",
            "четверг",
            "пятницу",
            "субботу",
            "воскресенье",
        ]
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        weekday_name = weekday_names_ru[target_dt.weekday()]
        formatted_date = target_dt.strftime("%d.%m.%Y")

        tasks_list = "\n".join([f"- {task}" for task in moved_tasks_info])
        success_msg = f"Перенесено {tasks_moved} задач на {weekday_name} ({formatted_date}):\n{tasks_list}"

        await context.bot.send_message(chat_id=chat_id, text=success_msg)

    except Exception as e:
        logger.error(f"Error handling task rescheduling: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Произошла ошибка при обработке запроса на перенос задач.",
        )


async def get_rescheduling_parameters(
    message_text: str, system_instruction: str
) -> Dict[str, Any]:
    """Use LLM to extract rescheduling parameters from the message."""
    try:
        # For now, simulate LLM analysis with simple logic
        # In production, this should call llm_handler with proper prompting

        text_lower = message_text.lower()
        result = {}

        # Extract task query - what to reschedule
        if "не важные" in text_lower or "неважные" in text_lower:
            result["task_query"] = "не важные задачи"
            result["is_low_priority_only"] = True
        elif "гвозди" in text_lower:
            result["task_query"] = "гвозди"
        elif "стройк" in text_lower:
            result["task_query"] = "стройка"
            result["search_by_project"] = True
            result["project_name"] = "Стройка"
        else:
            # Extract query between "перенеси" and "на"
            parts = text_lower.split("перенеси", 1)
            if len(parts) > 1:
                query_part = parts[1]
                if " на " in query_part:
                    result["task_query"] = query_part.split(" на ")[0].strip()
                else:
                    result["task_query"] = query_part.strip()

        # Extract target date
        if "завтра" in text_lower:
            result["target_date"] = "tomorrow"
        elif "послезавтра" in text_lower:
            result["target_date"] = "+2 days"
        elif "вторник" in text_lower:
            if "след" in text_lower or "следующ" in text_lower:
                result["target_date"] = "next Tuesday"
            else:
                result["target_date"] = "Tuesday"
        elif "три дня" in text_lower or "3 дня" in text_lower:
            result["target_date"] = "+3 days"

        # TODO: Replace this with actual LLM call using system_instruction
        # Here's where you'd call the LLM:
        # analysis_result = llm_handler.analyze_text_with_system_instruction(message_text, system_instruction)

        return result

    except Exception as e:
        logger.error(f"Error extracting rescheduling parameters: {e}", exc_info=True)
        return {}


async def resolve_target_date(target_date_str: str) -> Optional[str]:
    """Convert a relative or named date to a YYYY-MM-DD format."""
    try:
        today = datetime.now().date()

        # Already in correct format
        if (
            target_date_str
            and len(target_date_str) == 10
            and target_date_str[4] == "-"
            and target_date_str[7] == "-"
        ):
            return target_date_str

        # Handle relative dates
        if target_date_str == "tomorrow":
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")

        if target_date_str.startswith("+"):
            try:
                days = int(target_date_str.split("+")[1].split(" ")[0])
                return (today + timedelta(days=days)).strftime("%Y-%m-%d")
            except (ValueError, IndexError):
                pass

        # Handle day names
        day_mapping = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
            "понедельник": 0,
            "вторник": 1,
            "среда": 2,
            "четверг": 3,
            "пятница": 4,
            "суббота": 5,
            "воскресенье": 6,
        }

        for day_name, weekday_num in day_mapping.items():
            if day_name in target_date_str.lower():
                # Calculate days until this weekday
                days_ahead = weekday_num - today.weekday()
                if days_ahead <= 0:  # Target day already happened this week
                    days_ahead += 7

                # If "next" is specified, add an additional week
                if (
                    "next" in target_date_str.lower()
                    or "след" in target_date_str.lower()
                ):
                    days_ahead += 7

                target_date = today + timedelta(days=days_ahead)
                return target_date.strftime("%Y-%m-%d")

        # Could not parse
        return None

    except Exception as e:
        logger.error(f"Error resolving target date: {e}", exc_info=True)
        return None


async def find_and_reschedule_tasks(
    task_query: str,
    target_date: str,
    is_low_priority: bool = False,
    search_by_project: bool = False,
    project_name: str = "",
) -> Tuple[int, List[str]]:
    """
    Find tasks matching the query and reschedule them to the target date.

    Returns:
        Tuple of (number of tasks moved, list of moved task names)
    """
    try:
        api_client = todoist_handler._init_api()
        if not api_client:
            return 0, []

        # Get all active tasks
        all_tasks = api_client.get_tasks()

        # Filter tasks based on criteria
        matching_tasks = []
        project_id = None

        # If searching by project, find project ID first
        if search_by_project and project_name:
            projects = todoist_handler.get_projects()
            for project in projects:
                if project_name.lower() in project["name"].lower():
                    project_id = project["id"]
                    break

        # Match tasks based on criteria
        for task in all_tasks:
            matches = False

            # Match by priority if needed
            if (
                is_low_priority and task.priority == 4
            ):  # 4 is lowest priority in Todoist
                matches = True

            # Match by project if needed
            elif search_by_project and project_id and task.project_id == project_id:
                matches = True

            # Match by content/name
            elif task_query.lower() in task.content.lower():
                matches = True

            if matches:
                matching_tasks.append(task)

        # Reschedule matching tasks
        moved_tasks = []
        moved_task_names = []

        for task in matching_tasks:
            try:
                api_client.update_task(task_id=task.id, due_date=target_date)
                moved_tasks.append(task)
                moved_task_names.append(task.content)
                logger.info(f"Moved task '{task.content}' to {target_date}")
            except Exception as e:
                logger.error(f"Error moving task {task.id}: {e}")

        return len(moved_tasks), moved_task_names

    except Exception as e:
        logger.error(f"Error finding and rescheduling tasks: {e}", exc_info=True)
        return 0, []


async def improve_with_llm():
    """
    In a production system, this module would use the LLM for:
    1. Extracting task rescheduling parameters with greater accuracy
    2. Finding semantic matches between user queries and tasks
    3. Improved date parsing for various natural language formats
    4. Understanding complex scheduling requests

    The current implementation contains simplified logic as placeholders
    where LLM calls would be implemented.
    """
    pass
