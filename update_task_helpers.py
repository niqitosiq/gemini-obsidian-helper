import logging
import asyncio
from datetime import datetime

# Import ContextTypes and Application
from telegram.ext import ContextTypes, Application
import todoist_handler
import llm_handler  # Add this import

logger = logging.getLogger(__name__)


# Modify signature to accept context
async def update_task_duration(
    application: Application,
    chat_id: int,
    task_id: str,
    duration_minutes: int,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Update a task with the provided duration."""  # Removed "and trigger rescheduling"
    try:
        # Get the API client
        api_client = todoist_handler._init_api()
        if not api_client:
            logger.error(
                f"Failed to initialize Todoist API for task {task_id} duration update."
            )
            await application.bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось связаться с Todoist для обновления задачи.",
            )
            return False

        # Prepare task parameters for duration update
        task_params = {"duration": duration_minutes, "duration_unit": "minute"}

        # Update the task
        api_client.update_task(task_id=task_id, **task_params)
        logger.info(
            f"Updated task {task_id} with duration: {duration_minutes} minutes via API."
        )

        # Confirm to the user using LLM
        confirm_msg = await llm_handler.generate_response(
            prompt_type="duration_update_success",
            data={"duration_minutes": duration_minutes},
        )
        await application.bot.send_message(
            chat_id=chat_id,
            text=confirm_msg
            or f"✅ Продолжительность задачи обновлена на {duration_minutes} минут.",
        )

        return True

    except Exception as e:
        logger.error(f"Error updating task duration for {task_id}: {e}", exc_info=True)
        # Use LLM for error message
        fail_msg = await llm_handler.generate_response(
            prompt_type="duration_update_fail", data={}
        )
        await application.bot.send_message(
            chat_id=chat_id,
            text=fail_msg or "❌ Не удалось обновить продолжительность задачи.",
        )
        return False
