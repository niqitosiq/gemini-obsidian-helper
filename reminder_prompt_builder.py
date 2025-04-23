import logging
import datetime
import json
import os
from typing import Dict, Any, Optional, List
from google.genai import types
from prompt_builder import _get_tool_call_example, _get_instructions

logger = logging.getLogger(__name__)

# Path to conversation history file
CONVERSATION_HISTORY_FILE = "conversation_history.json"


def _get_reminder_template() -> str:
    """
    Returns the template for reminders sent to the LLM.
    """
    return """A scheduled task reminder has been triggered:

Task: {title}
Due: {date} {time_str}
Details: {description}

The system needs to remind the user about this task. Use the task information and any available context in the user's workspace to provide a helpful reminder. Consider:
- The task's relationship to other tasks in the system
- Any recent discussions related to this task
- Current time and date context
- Appropriate next actions for the task
- Use Markdown formatting for the response
"""


def _format_reminder_context(task_data: Dict[str, Any]) -> str:
    """
    Format task data into a reminder context.

    Args:
        task_data: Dictionary with task details

    Returns:
        Formatted string with task context
    """
    context = f"Task: {task_data.get('title', 'Untitled Task')}\n"

    if "description" in task_data and task_data["description"]:
        context += f"Description: {task_data['description']}\n"

    if "date" in task_data and task_data["date"]:
        context += f"Date: {task_data['date']}\n"

    if "startTime" in task_data and task_data["startTime"]:
        context += f"Time: {task_data['startTime']}\n"

    if "status" in task_data and task_data["status"]:
        context += f"Status: {task_data['status']}\n"

    if "priority" in task_data and task_data["priority"]:
        context += f"Priority: {task_data['priority']}\n"

    return context


def get_reminder_prompt(
    task_title: str,
    task_description: Optional[str] = None,
    scheduled_date: Optional[str] = None,
    scheduled_time: Optional[str] = None,
) -> str:
    """
    Generate a prompt for a task reminder.

    Args:
        task_title: Title of the task
        task_description: Description of the task (optional)
        scheduled_date: Date when the task is scheduled (optional)
        scheduled_time: Time when the task is scheduled (optional)

    Returns:
        A formatted prompt string for the reminder
    """
    # Use current date/time if not provided
    if not scheduled_date:
        scheduled_date = datetime.datetime.now().strftime("%Y-%m-%d")

    # Format the time string if available
    time_str = f"at {scheduled_time}" if scheduled_time else ""

    # Use placeholder if description not provided
    description = (
        task_description if task_description else "No additional details provided."
    )

    # Format using the template
    reminder = _get_reminder_template().format(
        title=task_title,
        description=description,
        date=scheduled_date,
        time_str=time_str,
    )

    # Log the reminder generation
    logger.debug(f"Generated reminder prompt for task: {task_title}")

    return reminder


def _get_conversation_context(task_title: str, limit: int = 10) -> str:
    """
    Retrieves relevant conversation history related to a task.

    Args:
        task_title: Title of the task to find relevant conversations for
        limit: Maximum number of conversation entries to include

    Returns:
        String containing relevant conversation history or empty string if none found
    """
    try:
        if not os.path.exists(CONVERSATION_HISTORY_FILE):
            logger.warning(
                f"Conversation history file not found: {CONVERSATION_HISTORY_FILE}"
            )
            return ""

        with open(CONVERSATION_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

        if not history or not isinstance(history, list):
            logger.warning("Conversation history is empty or not in expected format")
            return ""

        # Find conversations related to this task (case-insensitive search)
        relevant_entries = []
        task_keywords = task_title.lower().split()

        # Add most recent entries and any entries relevant to the task
        for entry in reversed(history[-30:]):  # Check last 30 entries
            if "parts" not in entry or not entry["parts"]:
                continue

            # Get text content from the entry
            text = ""
            for part in entry["parts"]:
                if isinstance(part, dict) and "text" in part:
                    text += part["text"] + " "
                elif isinstance(part, str):
                    text += part + " "

            # Check if this entry is relevant to our task
            is_relevant = False
            if any(keyword in text.lower() for keyword in task_keywords):
                is_relevant = True

            # Add entry if relevant
            if is_relevant:
                role = entry.get("role", "unknown")
                relevant_entries.append(f"{role}: {text.strip()}")

            # Limit the number of entries
            if len(relevant_entries) >= limit:
                break

        if not relevant_entries:
            return ""

        # Format the conversation context
        context = "Recent related conversation:\n\n"
        context += "\n\n".join(relevant_entries)
        return context

    except Exception as e:
        logger.error(f"Error retrieving conversation context: {e}", exc_info=True)
        return ""


def build_reminder_context(task_data: Dict[str, Any]) -> types.Content:
    """
    Build a context object for a reminder that can be passed to the LLM.

    Args:
        task_data: Dictionary containing task information

    Returns:
        Content object with the reminder formatted as user input
    """
    # Extract key information
    title = task_data.get("title", "Untitled Task")
    description = task_data.get("description", "")
    date = task_data.get("date", datetime.datetime.now().strftime("%Y-%m-%d"))
    time = task_data.get("startTime", "")

    # Get conversation context related to this task
    conversation_context = _get_conversation_context(title)

    # Generate the reminder prompt
    reminder_text = get_reminder_prompt(
        task_title=title,
        task_description=description,
        scheduled_date=date,
        scheduled_time=time,
    )

    # Add conversation context if available
    if conversation_context:
        reminder_text += f"\n\n{conversation_context}"

    reminder_text += f"""
Example Of The Response (Creating and Linking Two Tasks):
{_get_tool_call_example()}

Instructions:
{_get_instructions()}"""

    # Create a content object with the user role
    return types.Content(role="user", parts=[types.Part(text=reminder_text)])
