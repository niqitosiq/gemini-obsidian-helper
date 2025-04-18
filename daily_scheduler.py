import logging
from datetime import datetime, time, timedelta, date
from typing import List, Dict, Optional, Tuple  # Added Tuple
import todoist_handler
import config
import utils  # Assuming utils.py has is_working_time
import math  # Added math for rounding
import asyncio  # Added asyncio for sleep
import llm_handler  # Added llm_handler import
from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # Added button imports
from typing import Optional, Union, List, Dict, Any
from todoist_api_python.models import Task  # Ensure Task is imported

# --- FIX: Import ContextTypes ---
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Types of day for activity suggestions (keep for context)
WORKDAY = "workday"
WEEKEND = "weekend"
HOLIDAY = "holiday"

# --- NEW: Configuration for scheduling behavior ---
TASK_BUFFER_MINUTES = 15  # Minutes buffer after each task
ROUND_TO_MINUTES = 15  # Round proposed time up to nearest 15 minutes


# --- NEW: Helper function to round time up ---
def _round_time_up(dt: datetime, interval_minutes: int) -> datetime:
    """Rounds a datetime object up to the nearest interval."""
    if interval_minutes <= 0:
        return dt
    # Calculate minutes past the last interval
    minutes_past_interval = (dt.minute * 60 + dt.second + dt.microsecond / 1e6) % (
        interval_minutes * 60
    )
    if minutes_past_interval == 0:
        return dt  # Already on the interval

    # Calculate minutes to add to reach the next interval
    minutes_to_add = interval_minutes - (minutes_past_interval / 60)
    # Use ceiling to ensure we always round up if not exactly on the interval
    rounded_minutes_to_add = math.ceil(minutes_to_add)

    # Create the rounded datetime
    rounded_dt = dt + timedelta(minutes=rounded_minutes_to_add)
    # Set seconds and microseconds to 0 for cleanliness
    rounded_dt = rounded_dt.replace(second=0, microsecond=0)

    return rounded_dt


async def create_daily_schedule(
    telegram_bot_app, chat_id: int = None, context: ContextTypes.DEFAULT_TYPE = None
) -> None:
    """
    Creates a daily schedule for the user and sends it via Telegram.
    This is meant to be run every morning.

    Args:
        telegram_bot_app: The Telegram bot application instance
        chat_id: The Telegram chat ID to send the schedule to (optional)
        context: The Telegram bot context (optional, used for setting state)
    """
    logger.info("Starting daily schedule creation")

    # Get chat_id from config if not provided
    if not chat_id and config.TELEGRAM_USER_ID:
        chat_id = config.TELEGRAM_USER_ID

    if not chat_id:
        logger.error(
            "No chat_id provided or found in config. Cannot send daily schedule."
        )
        return

    # Determine if today is a workday or weekend
    today = datetime.now().date()
    day_type = get_day_type(today)

    # 1. Get today's already scheduled tasks
    today_tasks = get_today_tasks()

    # 2. Calculate available time blocks (now includes buffers)
    available_blocks = calculate_available_time_blocks(today_tasks, day_type)

    # 3. Get pending tasks that should be scheduled, passing context to filter skipped
    pending_tasks = get_pending_tasks(day_type, context)  # Pass context

    # Log information about found tasks
    logger.info(f"Found {len(pending_tasks)} pending tasks to schedule")
    today_tasks_count = len([t for t in pending_tasks if t.get("due_today")])
    overdue_tasks_count = len([t for t in pending_tasks if t.get("overdue")])
    logger.info(
        f"Tasks due today: {today_tasks_count}, Overdue tasks: {overdue_tasks_count}"
    )

    # If not enough tasks, consider adding tasks from the backlog
    # Make sure we have enough tasks for a productive day
    if today_tasks_count + overdue_tasks_count < 3:
        logger.info("Not enough tasks for today, checking backlog")
        # We'll handle backlog recommendation in the create_schedule function

    # 4. Create schedule suggestions and identify tasks needing clarification
    suggestions, need_clarification_tasks = create_schedule(
        pending_tasks, available_blocks, day_type
    )

    # 5. Format and send messages using LLM
    try:
        # Generate and send introduction message via LLM
        intro_message = await llm_handler.generate_response(
            prompt_type="schedule_intro",
            data={"day_type": day_type, "date": today.strftime("%Y-%m-%d")},
        )
        if intro_message:
            await telegram_bot_app.bot.send_message(chat_id=chat_id, text=intro_message)
        else:
            logger.warning("LLM failed to generate schedule introduction.")

        # --- Handle Suggestions ---
        if suggestions:
            first_suggestion = suggestions[0]
            task_content = first_suggestion["task"]["content"]
            proposed_time = first_suggestion["proposed_start"]
            task_id = first_suggestion["task"]["id"]

            # Generate suggestion message via LLM
            suggestion_message = await llm_handler.generate_response(
                prompt_type="suggest_schedule_slot",
                data={
                    "task_content": task_content,
                    "proposed_time": proposed_time.strftime("%H:%M"),
                    "date": proposed_time.strftime("%Y-%m-%d"),
                },
            )
            if not suggestion_message:
                logger.warning("LLM failed to generate suggestion message.")
                # Fallback message
                suggestion_message = f"Предлагаю запланировать '{task_content}' на {proposed_time.strftime('%H:%M')} сегодня. Назначить?"

            # Create Inline Keyboard with "Finish" button
            keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ Назначить",
                        callback_data=f"schedule_{task_id}_{proposed_time.isoformat()}",
                    ),
                    InlineKeyboardButton(
                        "❌ Пропустить", callback_data=f"skip_{task_id}"
                    ),
                ],
                [
                    # Add Finish button spanning the row
                    InlineKeyboardButton(
                        "🏁 Закончить планирование", callback_data="finish_planning"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send suggestion with keyboard
            await telegram_bot_app.bot.send_message(
                chat_id=chat_id, text=suggestion_message, reply_markup=reply_markup
            )

            # Set state for callback handler
            if context:
                context.user_data["waiting_for_schedule_confirmation"] = (
                    first_suggestion
                )
                logger.info(
                    f"Set 'waiting_for_schedule_confirmation' state for task {task_id} at {proposed_time}"
                )
            else:
                logger.warning(
                    "Context not provided, cannot set schedule confirmation state."
                )

        # --- Handle Clarifications (if no suggestions were made) ---
        elif need_clarification_tasks:
            task_to_clarify = need_clarification_tasks[0]
            # Generate clarification question via LLM
            clarification_message = await llm_handler.generate_response(
                prompt_type="clarify_duration",
                data={"task_content": task_to_clarify["content"]},
            )

            if not clarification_message:
                logger.warning("LLM failed to generate clarification question.")
                # Fallback question
                clarification_message = (
                    f"Сколько времени займет задача '{task_to_clarify['content']}'?"
                )

            # Add a small delay before asking the question if a schedule was also sent
            if suggestions:
                await asyncio.sleep(1)
            await telegram_bot_app.bot.send_message(
                chat_id=chat_id, text=clarification_message
            )

            # Set the state in context if context is provided
            if context:
                context.user_data["waiting_for_duration"] = (
                    task_to_clarify  # Store the whole task dict
                )
                logger.info(
                    f"Set 'waiting_for_duration' state for task ID {task_to_clarify.get('id', 'N/A')}"
                )
            else:
                logger.warning(
                    "Context not provided to create_daily_schedule, cannot set 'waiting_for_duration' state."
                )

        # --- Handle No Actions ---
        else:
            # Generate "nothing to schedule" message via LLM
            nothing_message = await llm_handler.generate_response(
                prompt_type="schedule_body",  # Use schedule_body with empty data
                data={
                    "scheduled_tasks": [],
                    "needs_clarification": False,
                    "day_type": day_type,
                },
            )
            if nothing_message:
                await telegram_bot_app.bot.send_message(
                    chat_id=chat_id, text=nothing_message
                )
            else:
                # Fallback
                await telegram_bot_app.bot.send_message(
                    chat_id=chat_id,
                    text="Нет задач для планирования или предложений на сегодня.",
                )

    except Exception as e:
        logger.error(f"Error sending daily schedule: {e}", exc_info=True)
        # Send error message via LLM? Or keep simple?
        await telegram_bot_app.bot.send_message(
            chat_id=chat_id, text="Произошла ошибка при создании расписания."
        )


def get_day_type(date: datetime.date) -> str:
    """Determine if the given date is a workday, weekend or holiday."""
    # Check if it's a weekend (6 = Saturday, 7 = Sunday in isoweekday)
    if date.isoweekday() not in config.WORK_DAYS:
        return WEEKEND

    # TODO: Add holiday detection if needed
    return WORKDAY


def get_today_tasks() -> list[todoist_handler.Task]:
    """Fetches ALL active tasks and filters for those scheduled today with specific times."""
    logger.debug("Fetching all active tasks to filter for today's schedule...")
    try:
        all_tasks = todoist_handler.get_tasks()  # Should now return list[Task]

        today_date = datetime.now().date()
        tasks_with_time_today = []
        for task in all_tasks:
            # --- FIX: Add type check ---
            if not isinstance(task, Task):
                logger.warning(
                    f"Skipping non-Task item in get_today_tasks loop: {type(task)}"
                )
                continue
            # --- END FIX ---

            # Original filtering logic
            if task.due and task.due.date == str(today_date) and task.due.datetime:
                tasks_with_time_today.append(task)

        logger.info(
            f"Found {len(tasks_with_time_today)} tasks with specific due times today after filtering."
        )
        return tasks_with_time_today
    except Exception as e:
        logger.error(f"Error fetching or filtering today's tasks: {e}", exc_info=True)
        return []


def calculate_available_time_blocks(
    today_tasks: List[Dict[str, Any]], day_type: str
) -> List[Dict[str, Any]]:
    """Calculate available time blocks for scheduling, including buffers."""
    today = datetime.now().date()
    now = datetime.now()

    # Set work hours based on day type
    if day_type == WORKDAY:
        start_hour = config.WORK_START_HOUR
        end_hour = config.WORK_END_HOUR
    else:  # Weekend/holiday - use wider time range
        start_hour = 10
        end_hour = 20

    # Start time is the maximum of current time or work day start, rounded up
    day_start_raw = datetime.combine(today, time(start_hour, 0))
    search_start_time = max(now, day_start_raw)
    # --- MODIFICATION: Round start time up ---
    day_start = _round_time_up(search_start_time, ROUND_TO_MINUTES)
    logger.debug(f"Effective search start time rounded to: {day_start}")

    day_end = datetime.combine(today, time(end_hour, 0))

    # If rounded start time is already past the end time, no blocks available
    if day_start >= day_end:
        logger.warning(
            "Start time is past end time after rounding, no blocks available."
        )
        return []

    # Create initial block covering the whole available period
    blocks = [{"start": day_start, "end": day_end}]

    # Split blocks by existing tasks, adding buffer
    for task in today_tasks:
        task_start = task["start_time"]
        # --- MODIFICATION: Add buffer to task end time ---
        task_end_with_buffer = task["end_time"] + timedelta(minutes=TASK_BUFFER_MINUTES)

        new_blocks = []
        for block in blocks:
            block_start = block["start"]
            block_end = block["end"]

            # Check for overlap (task_start < block_end and task_end_with_buffer > block_start)
            if task_start < block_end and task_end_with_buffer > block_start:
                # Add block before the task if there's space
                if task_start > block_start:
                    new_blocks.append({"start": block_start, "end": task_start})
                # Add block after the task (with buffer) if there's space
                if task_end_with_buffer < block_end:
                    new_blocks.append({"start": task_end_with_buffer, "end": block_end})
            else:
                # No overlap, keep the block as is
                new_blocks.append(block)
        blocks = new_blocks  # Update blocks list for next iteration

    # Calculate duration and filter out too short blocks
    final_blocks = []
    min_block_duration = max(15, ROUND_TO_MINUTES)  # Minimum block size
    for block in blocks:
        # Ensure start is not after end (can happen with buffers)
        if block["start"] >= block["end"]:
            continue
        duration_minutes = (block["end"] - block["start"]).total_seconds() / 60
        if duration_minutes >= min_block_duration:
            block["duration_minutes"] = duration_minutes
            final_blocks.append(block)

    # Sort by start time
    final_blocks.sort(key=lambda x: x["start"])
    logger.debug(f"Calculated available blocks: {final_blocks}")

    return final_blocks


def get_pending_tasks(
    day_type: str, context: ContextTypes.DEFAULT_TYPE = None
) -> List[Dict[str, Any]]:
    """Get pending tasks (without specific time) that could be scheduled today."""
    all_tasks_data = []
    today = datetime.now().date()
    # Get skipped task IDs from context (ensure it's a set of strings)
    skipped_ids_set = (
        context.user_data.get("skipped_in_session", set()) if context else set()
    )
    if skipped_ids_set:
        logger.debug(
            f"Filtering out skipped task IDs (from context): {skipped_ids_set}"
        )

    try:
        api_client = todoist_handler._init_api()
        if not api_client:
            return []
        active_tasks = api_client.get_tasks()
        logger.info(
            f"Retrieved {len(active_tasks)} active tasks from Todoist for pending check"
        )

        for task in active_tasks:
            task_id_str = str(task.id)  # Get string version of task ID

            # --- Filter: Skip tasks already skipped in this session (check string version) ---
            if task_id_str in skipped_ids_set:
                logger.debug(
                    f"Skipping task {task_id_str} - previously skipped in this session."
                )
                continue

            # --- Filter: Only consider tasks WITHOUT a specific time ---
            if task.due and task.due.datetime:
                logger.debug(
                    f"Skipping task {task_id_str} - already has specific time: {task.due.datetime}"
                )
                continue

            overdue = False
            due_today = False  # Task has only date or no date
            priority = task.priority if hasattr(task, "priority") else 4

            # Check due date status (if date exists)
            if task.due and task.due.date:
                try:
                    due_date_str = str(task.due.date)
                    task_date = datetime.fromisoformat(due_date_str).date()
                    if task_date < today:
                        overdue = True
                    elif task_date == today:
                        due_today = True  # Due today (no specific time yet)
                except ValueError:
                    logger.warning(
                        f"Could not parse due date '{task.due.date}' for task {task.id}"
                    )

            # --- Relevance Score (Keep existing logic) ---
            relevance_score = 0
            if overdue:
                relevance_score += 100
            elif due_today:
                relevance_score += 80

            if priority == 1:
                relevance_score += 50
            elif priority == 2:
                relevance_score += 30
            elif priority == 3:
                relevance_score += 15

            # --- Duration Extraction (Keep existing logic) ---
            duration_minutes = None
            try:
                if hasattr(task, "duration") and task.duration:
                    # Primary check: task.duration.amount and task.duration.unit
                    if hasattr(task.duration, "amount") and hasattr(
                        task.duration, "unit"
                    ):
                        amount = task.duration.amount
                        unit = task.duration.unit
                        if unit == "minute":
                            duration_minutes = amount
                        elif unit == "day":
                            logger.debug(
                                f"Task {task.id} duration is in days, treating as unknown."
                            )
                        else:
                            logger.warning(
                                f"Unknown duration unit '{unit}' for task {task.id}"
                            )
                    # Fallback: Check if task.duration is a dict (less likely)
                    elif (
                        isinstance(task.duration, dict)
                        and "amount" in task.duration
                        and "unit" in task.duration
                    ):
                        amount = task.duration["amount"]
                        unit = task.duration["unit"]
                        if unit == "minute":
                            duration_minutes = amount
            except Exception as e:
                logger.debug(
                    f"Could not extract duration for pending task {task.id}: {e}"
                )

            # Prepare task data (store original ID type)
            task_data = {
                "id": task.id,  # Store original ID
                "content": task.content,
                "project_id": task.project_id,
                "priority": priority,
                "relevance_score": relevance_score,
                "duration_minutes": duration_minutes,
                "needs_clarification": duration_minutes is None,
                "overdue": overdue,
                "due_today": due_today,
            }
            all_tasks_data.append(task_data)

    except Exception as e:
        logger.error(f"Error getting pending tasks: {e}", exc_info=True)

    # Sort tasks by relevance score (highest first)
    all_tasks_data.sort(key=lambda x: x["relevance_score"], reverse=True)

    # Apply day-specific boosts (Work/Fun projects)
    if day_type == WORKDAY:
        # Get work project IDs - could be configured or detected
        work_projects = get_work_projects()

        # Boost score for work tasks on workdays
        for task in all_tasks_data:
            if task["project_id"] in work_projects:
                task["relevance_score"] += 20
    else:
        # For weekends, prioritize non-work tasks
        work_projects = get_work_projects()
        fun_projects = get_fun_projects()

        # Boost fun tasks on weekends
        for task in all_tasks_data:
            if task["project_id"] not in work_projects:
                task["relevance_score"] += 10

            if task["project_id"] in fun_projects:
                task["relevance_score"] += 30

    # Re-sort after applying day-specific boosts
    all_tasks_data.sort(key=lambda x: x["relevance_score"], reverse=True)

    logger.info(f"Found {len(all_tasks_data)} pending, non-skipped tasks to consider.")
    # Log counts based on the collected data
    today_count = sum(1 for t in all_tasks_data if t["due_today"])
    overdue_count = sum(1 for t in all_tasks_data if t["overdue"])
    logger.info(
        f"Processed pending tasks - Due Today: {today_count}, Overdue: {overdue_count}"
    )

    return all_tasks_data


def get_work_projects() -> List[str]:
    """Get list of work-related project IDs."""
    # This is a placeholder - you should customize this to your specific projects
    work_related_keywords = ["work", "работа", "job", "project", "проект"]

    projects = todoist_handler.get_projects()
    work_projects = []

    for project in projects:
        name = project["name"].lower()
        if any(keyword in name for keyword in work_related_keywords):
            work_projects.append(project["id"])

    # If specific projects are known to be work-related, add them here
    # For example, based on your knowledge_base.md content:
    if "2285999515" not in work_projects:  # This seems to be a work project ID
        work_projects.append("2285999515")

    return work_projects


def get_fun_projects() -> List[str]:
    """Get list of fun/leisure project IDs."""
    # This is a placeholder - you should customize this to your specific projects
    fun_keywords = [
        "fun",
        "hobby",
        "personal",
        "развлечение",
        "хобби",
        "отдых",
        "leisure",
    ]

    projects = todoist_handler.get_projects()
    fun_projects = []

    for project in projects:
        name = project["name"].lower()
        if any(keyword in name for keyword in fun_keywords):
            fun_projects.append(project["id"])

    return fun_projects


def create_schedule(
    pending_tasks: List[Dict[str, Any]],
    available_blocks: List[Dict[str, Any]],
    day_type: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Identifies tasks needing clarification and suggests rounded slots for others.
    Returns:
        Tuple of (suggestions, tasks_needing_clarification)
    """
    suggestions = []
    need_clarification = []

    # Sort blocks by start time (easier to find the *first* available slot)
    sorted_blocks = sorted(available_blocks, key=lambda x: x["start"])

    # ... (existing separation of tasks_to_suggest and need_clarification) ...
    tasks_to_suggest = []
    for task in pending_tasks:
        if task["needs_clarification"]:
            need_clarification.append(task)
        else:
            tasks_to_suggest.append(task)
    tasks_to_suggest.sort(key=lambda x: x["relevance_score"], reverse=True)
    need_clarification.sort(
        key=lambda x: x["relevance_score"], reverse=True
    )  # Sort clarification too

    logger.info(
        f"Found {len(tasks_to_suggest)} tasks with duration to potentially suggest slots for."
    )
    logger.info(
        f"Found {len(need_clarification)} tasks needing duration clarification."
    )

    if not sorted_blocks:
        logger.warning("No available time blocks for scheduling suggestions")
        return [], need_clarification

    # Keep track of used blocks to avoid suggesting overlapping times in one run
    used_block_indices = set()

    for task in tasks_to_suggest:
        task_duration = task["duration_minutes"]
        found_slot = False

        # Iterate through available blocks by start time
        for i, block in enumerate(sorted_blocks):
            if i in used_block_indices:
                continue  # Skip blocks already used in this planning session

            # --- MODIFICATION: Round potential start time and check fit ---
            potential_start_raw = block["start"]
            proposed_start_time = _round_time_up(potential_start_raw, ROUND_TO_MINUTES)
            proposed_end_time = proposed_start_time + timedelta(minutes=task_duration)

            # Check if the rounded slot fits within the block
            if (
                proposed_start_time >= block["start"]
                and proposed_end_time <= block["end"]
            ):
                logger.info(
                    f"Found potential rounded slot for '{task['content']}' at {proposed_start_time.strftime('%H:%M')} within block {block['start'].strftime('%H:%M')}-{block['end'].strftime('%H:%M')}"
                )

                suggestions.append(
                    {
                        "task": task,
                        "proposed_start": proposed_start_time,
                        "block_id": id(block),  # Keep block id if needed
                    }
                )

                # Mark block as used (or update its remaining time - simpler to just mark as used for now)
                used_block_indices.add(i)
                found_slot = True
                break  # Move to the next task once a slot is found

        if not found_slot:
            logger.info(
                f"Could not find a suitable rounded slot for task '{task['content']}' (duration: {task_duration} min)"
            )

    # Sort suggestions by proposed start time before returning
    suggestions.sort(key=lambda x: x["proposed_start"])

    return suggestions, need_clarification


async def schedule_task_with_api(task_id: str, start_time: datetime) -> bool:
    """Schedule a task for a specific time using Todoist API."""
    try:
        api_client = todoist_handler._init_api()
        if not api_client:
            logger.error(f"API client not available for scheduling task {task_id}")
            return False

        due_string = start_time.strftime("%Y-%m-%d %H:%M")

        # Update the task with the new due date/time
        logger.debug(
            f"Calling Todoist API to update task {task_id} due_string to {due_string}"
        )
        api_client.update_task(task_id=task_id, due_string=due_string)
        # Add confirmation log
        logger.info(f"Successfully updated task {task_id} via API to {due_string}")
        return True

    except Exception as e:
        # Log the specific error
        logger.error(
            f"Error calling Todoist API to schedule task {task_id}: {e}", exc_info=True
        )
        return False


async def estimate_task_duration(task_content: str) -> int:
    """
    Use LLM to estimate task duration.

    Returns:
        Estimated duration in minutes
    """
    try:
        # Call LLM to estimate duration
        prompt = f"Based on the task name, estimate how long it would take to complete this task (in minutes): {task_content}"

        # Prepare a system instruction
        system_instruction = """You are helping estimate how long a task will take to complete. Based on the task name, estimate the time in minutes.
For common tasks, use these guidelines:
- Quick email/message responses: 5-10 minutes
- Brief planning: 15 minutes
- Short meetings: 30 minutes
- Standard meetings: 60 minutes
- Complex tasks: 90-180 minutes
- Major projects: Best broken into smaller tasks

Return ONLY the number of minutes as an integer, nothing else."""

        # TODO: Implement proper LLM duration estimation
        # For now, use a simple heuristic based on task length
        words = len(task_content.split())

        if words <= 3:
            return 30  # Short tasks default to 30 min
        elif words <= 6:
            return 60  # Medium tasks default to 60 min
        else:
            return 90  # Longer task descriptions default to 90 min

    except Exception as e:
        logger.error(f"Error estimating task duration: {e}")
        return scheduler.DEFAULT_DURATION_MINUTES
