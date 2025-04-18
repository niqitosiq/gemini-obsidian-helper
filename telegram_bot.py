import logging
import os
import tempfile
import asyncio
from typing import Optional

# Add re import (keep for now, might be useful elsewhere)
import re

# Add datetime for callback parsing
from datetime import datetime
from telegram import (
    Update,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    # ConversationHandler, # Remove ConversationHandler
    CallbackQueryHandler,  # Add this
)
from telegram.constants import ParseMode
import config
import llm_handler  # Import llm_handler
import scheduler
import knowledge_base
import semantic_task_manager
import todoist_handler  # Ensure this import is present and correct

# Import the missing function again
from update_task_helpers import update_task_duration

# Import daily_scheduler to trigger planning and schedule_task_with_api
from daily_scheduler import create_daily_schedule, schedule_task_with_api

logger = logging.getLogger(__name__)


# --- Commands ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if config.TELEGRAM_USER_ID and user.id != config.TELEGRAM_USER_ID:
        logger.warning(f"Unauthorized user {user.id} tried /start")
        return
    logger.info(f"User {user.id} started conversation")
    await update.message.reply_html(
        rf"Hi, {user.mention_html()}! 👋 Send me tasks via text or voice.",
        reply_markup=ReplyKeyboardRemove(),
    )
    # Remove state clearing related to ConversationHandler
    # context.user_data.pop("clarification_state", None)
    # return ConversationHandler.END # Remove return state
    # Clear our custom states including skipped list
    context.user_data.pop("waiting_for_duration", None)
    context.user_data.pop("waiting_for_schedule_confirmation", None)
    context.user_data.pop("skipped_in_session", None)  # Clear skipped list


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancels current clarification or suggestion dialog."""
    user = update.effective_user
    if config.TELEGRAM_USER_ID and user.id != config.TELEGRAM_USER_ID:
        # return ConversationHandler.END # Remove return state
        return

    logger.info(f"User {user.id} cancelled the conversation.")
    await update.message.reply_text(
        "Okay, cancelled the current operation.", reply_markup=ReplyKeyboardRemove()
    )
    # Clear our custom states including skipped list
    context.user_data.pop("waiting_for_duration", None)
    context.user_data.pop("waiting_for_schedule_confirmation", None)
    context.user_data.pop("skipped_in_session", None)  # Clear skipped list


# --- Message handling ---
async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:  # Return type is None now
    """Handles incoming text or voice messages."""
    user = update.effective_user
    message = update.message

    if config.TELEGRAM_USER_ID and user.id != config.TELEGRAM_USER_ID:
        logger.warning(f"Ignored message from unauthorized user {user.id}")
        return None

    text_to_analyze = None
    source = "telegram"
    conversation_history = context.user_data.get("conversation_history", [])

    if message.text:
        logger.info(f"Received text message from {user.id}: {message.text}")
        text_to_analyze = message.text
        conversation_history.append(f"User: {text_to_analyze}")

    elif message.voice:
        logger.info(
            f"Received voice message from {user.id} (Duration: {message.voice.duration}s)"
        )
        try:
            voice_file = await message.voice.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_audio:
                await voice_file.download_to_drive(temp_audio.name)
                audio_path = temp_audio.name
            logger.debug(f"Voice message saved to temporary file: {audio_path}")

            transcribed_text = llm_handler.transcribe_audio(audio_path)

            try:
                os.remove(audio_path)
                logger.debug(f"Temporary audio file deleted: {audio_path}")
            except OSError as e:
                logger.error(f"Error deleting temporary audio file {audio_path}: {e}")

            if transcribed_text and "[Transcription Error]" not in transcribed_text:
                text_to_analyze = transcribed_text
                conversation_history.append(f"User (Voice): {text_to_analyze}")
                await message.reply_text(f'Recognized: "{text_to_analyze}"')
            else:
                await message.reply_text(
                    "❌ Could not recognize speech in voice message."
                )
                knowledge_base.log_entry("transcription_failed", {"user_id": user.id})
                return None

        except Exception as e:
            logger.error(f"Error processing voice message: {e}", exc_info=True)
            await message.reply_text(
                "An error occurred while processing voice message."
            )
            return None
    else:
        logger.info(f"Received unsupported message type from {user.id}")
        await message.reply_text("Sorry, I only understand text and voice messages.")
        return None

    if text_to_analyze:
        # process_text_input now returns None or raises exceptions
        await process_text_input(
            update, context, text_to_analyze, source, conversation_history
        )
        context.user_data["conversation_history"] = conversation_history[-10:]

    # return None # No state to return


async def process_text_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    source: str,
    history: list[str],
):
    await update.message.reply_chat_action("typing")
    chat_id = update.effective_chat.id
    logger.debug(f"Processing text input: '{text}'")

    # Check if this is a response to a task duration clarification
    if "waiting_for_duration" in context.user_data:
        task_info = context.user_data.get("waiting_for_duration")
        if task_info:
            logger.info(
                f"Detected duration response for task: {task_info['content']}"
            )  # Log detection
            try:
                duration_minutes = await llm_handler.parse_duration_response(text)

                if duration_minutes is not None and duration_minutes > 0:
                    logger.info(
                        f"LLM parsed duration: {duration_minutes} minutes. Updating task..."
                    )
                    # Store task_id before potentially clearing state
                    task_id_to_update = task_info.get("id")
                    if not task_id_to_update:
                        logger.error("Task ID missing in waiting_for_duration state.")
                        await update.message.reply_text(
                            "Ошибка: не найден ID задачи для обновления."
                        )
                        context.user_data.pop(
                            "waiting_for_duration", None
                        )  # Clear broken state
                        return  # Return None implicitly

                    # Clear state *before* calling update_task_duration which triggers rescheduling
                    # This prevents the re-entrant scheduler call from seeing the old state
                    logger.debug(
                        "Clearing 'waiting_for_duration' state before updating task."
                    )
                    del context.user_data["waiting_for_duration"]

                    success = await update_task_duration(
                        context.application,
                        chat_id,
                        task_id_to_update,  # Use stored task_id
                        duration_minutes,
                        context,
                    )
                    if success:
                        logger.info(
                            "Task duration updated successfully. Update function triggered rescheduling. Returning."
                        )  # Log success return
                        # No need to clear state again, already done
                        return  # Return None implicitly
                    else:
                        logger.warning(
                            "Update task duration failed. Informing user and returning."
                        )  # Log update fail return
                        await update.message.reply_text(
                            "Не удалось обновить длительность в Todoist."
                        )
                        # State already cleared
                        return  # Return None implicitly
                else:
                    logger.warning(
                        f"LLM could not parse duration from '{text}'. Asking again and returning."
                    )  # Log parse fail return
                    await update.message.reply_text(
                        "Не удалось распознать длительность. Попробуйте указать число минут или часов (например, '45 минут', '2 часа', 'полтора часа')."
                    )
                    # Keep state by *not* clearing it here
                    return  # Return None implicitly
            except Exception as e:
                logger.error(
                    f"Error processing duration response: {e}", exc_info=True
                )  # Log exception return
                await update.message.reply_text(
                    "Произошла ошибка при обработке вашего ответа о длительности."
                )
                # Clear state on exception to avoid getting stuck
                context.user_data.pop("waiting_for_duration", None)
                return  # Return None implicitly
        else:
            logger.warning(
                "'waiting_for_duration' key exists but task_info is missing/falsy."
            )  # Edge case log
            context.user_data.pop("waiting_for_duration", None)  # Clear broken state

    # Check if waiting for schedule confirmation
    if "waiting_for_schedule_confirmation" in context.user_data:
        logger.warning(
            "Received text while waiting for schedule confirmation button. Replying and returning."
        )  # Log schedule conflict return
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки 'Назначить' или 'Пропустить' для предложенной задачи."
        )
        return  # Return None implicitly

    # --- Semantic Command Check ---
    logger.debug(
        "Input not a duration response or schedule conflict. Checking for semantic command..."
    )
    try:
        # Check if the message is a semantic command
        is_semantic, command_type = (
            await semantic_task_manager.check_semantic_command_type(text)
        )

        if is_semantic:
            # If it's a planning command, clear the skipped list for a new session
            if command_type == "schedule_day":
                logger.info(
                    "Detected 'schedule_day' command, clearing skipped_in_session list."
                )
                context.user_data.pop("skipped_in_session", None)

            # Process the command (which might call create_daily_schedule)
            processed = await semantic_task_manager.process_semantic_command(
                update, context, text
            )
            if processed:
                logger.info("Input handled as semantic command. Returning.")
                history.append(f"Assistant: Processed semantic command: {text}")
                context.user_data["conversation_history"] = history[-10:]
                return  # Return None implicitly
            else:
                logger.warning("Semantic command detected but processing failed.")
                # Fall through to regular analysis? Or stop? Let's stop for now.
                await update.message.reply_text("Не удалось обработать команду.")
                return

    except Exception as e:
        logger.error(f"Error processing semantic command: {e}", exc_info=True)
        # Continue to regular analysis

    # --- Regular Task Analysis ---
    logger.debug(
        "Input not a semantic command. Proceeding with regular task analysis..."
    )
    tasks = llm_handler.analyze_text_batch(text, source, history)

    if not tasks:
        logger.warning(
            f"LLM analysis returned no tasks for input: '{text}'. Informing user."
        )
        await update.message.reply_text(
            "Не удалось проанализировать ваш запрос. Попробуйте переформулировать."
            if any(char in text for char in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
            else "Could not analyze your request. Please try rephrasing."
        )
        return  # Return None implicitly

    first_clarification_asked = False
    clarification_needed = False

    # Process each task sequentially
    for task in tasks:
        source_text = task.get("source_text", text)
        status = task.get("status")

        if status == "complete":
            logger.info(
                f"LLM analyzed task as complete: {task.get('action')} (from: {source_text})"
            )
            try:  # Add try-except block for safety
                # --- FIX: Ensure todoist_handler is accessible ---
                # The import should be at the top level, this call failed previously
                created_task = todoist_handler.create_task(
                    content=task.get("action"),
                    description=task.get("details"),
                    due_string=task.get(
                        "start_time"
                    ),  # Assuming start_time is used as due_string
                    priority=task.get("priority"),
                    project_id=task.get("project_id"),
                    duration_minutes=task.get("estimated_duration_minutes"),
                )
                if created_task:
                    project_name = "Входящие"  # Default
                    # --- FIX: Ensure todoist_handler is accessible ---
                    projects = todoist_handler.get_projects()
                    for p in projects:
                        if p["id"] == created_task.project_id:
                            project_name = p["name"]
                            break
                    confirm_msg = await llm_handler.generate_response(
                        prompt_type="task_creation_success",
                        data={
                            "content": created_task.content,
                            "project_name": project_name,
                            "due_string": (
                                created_task.due.string
                                if created_task.due
                                else "без срока"
                            ),
                        },
                    )
                    await update.message.reply_text(confirm_msg or "Задача создана.")
                else:
                    fail_msg = await llm_handler.generate_response(
                        prompt_type="task_creation_fail", data={}
                    )
                    await update.message.reply_text(
                        fail_msg or "Не удалось создать задачу."
                    )
            except NameError as ne:
                logger.error(
                    f"NameError during task creation/project fetch: {ne}. Is 'todoist_handler' imported correctly?",
                    exc_info=True,
                )
                await update.message.reply_text(
                    "Произошла внутренняя ошибка при доступе к Todoist."
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error during task creation: {e}", exc_info=True
                )
                await update.message.reply_text("Произошла ошибка при создании задачи.")

        elif status == "incomplete":
            clarification_needed = True
            # If this is the first incomplete task, ask about it right away
            if not first_clarification_asked:
                question = task.get("clarification_question", "Could you clarify?")
                task_action = task.get("action", "Задача")

                await update.message.reply_text(f"📝 {task_action}: {question}")
                first_clarification_asked = True
                history.append(f"Assistant: {question}")
                # Set state for duration clarification if that's the missing info
                # This logic might need refinement based on actual missing_info
                if "duration" in str(task.get("missing_info", [])).lower():
                    context.user_data["waiting_for_duration"] = task  # Store task info
                    logger.info(
                        f"Set 'waiting_for_duration' state for incomplete task: {task_action}"
                    )
                # else: handle other types of clarification?
                # return # Return None implicitly - stop after first question

    logger.debug("Finished processing tasks from LLM analysis.")


# --- Callback Query Handler ---
async def button_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles button presses for schedule suggestions."""
    query = update.callback_query
    # Answer the callback query immediately to remove the "loading" state on the button
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Failed to answer callback query: {e}")
        # Continue processing even if answering fails

    callback_data = query.data
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    logger.info(
        f"Received button callback with data: '{callback_data}' for message {message_id}"
    )

    # --- Handle Finish Planning Action ---
    if callback_data == "finish_planning":
        logger.info("User requested to finish planning.")
        # Clear relevant states
        context.user_data.pop("waiting_for_schedule_confirmation", None)
        context.user_data.pop("waiting_for_duration", None)
        context.user_data.pop("skipped_in_session", None)
        try:
            await query.edit_message_text(text="👌 Планирование завершено.")
            logger.debug(f"Edited message {message_id} to 'Планирование завершено.'")
        except Exception as e:
            logger.error(
                f"Failed to edit message {message_id} for finish_planning: {e}"
            )
        return

    # --- Check State BEFORE processing schedule/skip ---
    if "waiting_for_schedule_confirmation" not in context.user_data:
        logger.warning(
            f"Received callback '{callback_data}' but 'waiting_for_schedule_confirmation' not in user_data. Message might be outdated."
        )
        try:
            # Check if the message wasn't already edited to the "finished" state
            if query.message.text != "👌 Планирование завершено.":
                await query.edit_message_text(text="Этот выбор больше не актуален.")
                logger.debug(
                    f"Edited message {message_id} to 'Этот выбор больше не актуален.'"
                )
            else:
                logger.debug(
                    f"Message {message_id} already shows 'Планирование завершено.', not editing."
                )
        except Exception as e:
            logger.error(
                f"Failed to edit message {message_id} for 'not waiting' state: {e}"
            )
        return

    # --- Handle Schedule/Skip Actions ---
    suggestion_data = context.user_data.get(
        "waiting_for_schedule_confirmation"
    )  # Use .get() for safety
    if not suggestion_data:
        # This case should theoretically be caught by the check above, but added for robustness
        logger.error(
            "'waiting_for_schedule_confirmation' key exists but data is missing/falsy."
        )
        context.user_data.pop(
            "waiting_for_schedule_confirmation", None
        )  # Clear broken state
        try:
            await query.edit_message_text(text="Ошибка состояния. Попробуйте снова.")
        except Exception as e:
            logger.error(
                f"Failed to edit message {message_id} for missing suggestion_data: {e}"
            )
        return

    # Pop the state *after* verifying it's relevant to this callback
    # suggestion_data = context.user_data.pop("waiting_for_schedule_confirmation") # Moved pop lower

    task_info = suggestion_data.get("task", {})
    task_id = task_info.get("id")
    task_content = task_info.get("content", "задача")

    if task_id is None:
        logger.error("Task ID missing in schedule confirmation state data.")
        context.user_data.pop(
            "waiting_for_schedule_confirmation", None
        )  # Clear broken state
        try:
            await query.edit_message_text(
                text="Ошибка: не найден ID задачи для подтверждения."
            )
        except Exception as e:
            logger.error(
                f"Failed to edit message {message_id} for missing task_id: {e}"
            )
        return

    # Parse callback data
    try:
        action, data_task_id, *time_data = callback_data.split("_")
    except ValueError:
        logger.warning(f"Could not parse callback data: {callback_data}")
        # Don't clear state here, maybe it was a different button?
        try:
            # Edit the message associated with *this* button press
            await query.edit_message_text(text="Ошибка обработки данных кнопки.")
        except Exception as e:
            logger.error(
                f"Failed to edit message {message_id} for callback parse error: {e}"
            )
        return

    # Verify the callback data matches the task we are currently waiting for
    if data_task_id != str(task_id):
        logger.warning(
            f"Callback task ID '{data_task_id}' does not match state task ID '{task_id}'. Ignoring."
        )
        try:
            # Edit the message associated with *this* button press
            await query.edit_message_text(text="Этот выбор относится к другой задаче.")
            logger.debug(
                f"Edited message {message_id} to 'Этот выбор относится к другой задаче.'"
            )
        except Exception as e:
            logger.error(
                f"Failed to edit message {message_id} for mismatched task ID: {e}"
            )
        # Do not clear the state, as it belongs to a different suggestion message
        return

    # --- If checks pass, NOW pop the state and process the action ---
    logger.debug(
        f"Callback data matches state for task {task_id}. Popping state and processing action '{action}'."
    )
    context.user_data.pop("waiting_for_schedule_confirmation")

    if action == "schedule":
        try:
            proposed_time_str = time_data[0]
            proposed_time = datetime.fromisoformat(proposed_time_str)
            logger.info(f"User accepted schedule for task {task_id} at {proposed_time}")

            # Schedule the task via API
            success = await schedule_task_with_api(task_id, proposed_time)
            response_text = ""
            if success:
                confirm_msg = await llm_handler.generate_response(
                    prompt_type="schedule_confirm",
                    data={
                        "task_content": task_content,
                        "scheduled_time": proposed_time.strftime("%H:%M"),
                    },
                )
                response_text = (
                    confirm_msg or f"✅ Задача '{task_content}' запланирована."
                )
            else:
                response_text = (
                    f"❌ Не удалось запланировать задачу '{task_content}' в Todoist."
                )

            try:
                await query.edit_message_text(text=response_text)
                logger.debug(f"Edited message {message_id} after schedule action.")
            except Exception as e:
                logger.error(
                    f"Failed to edit message {message_id} after schedule action: {e}"
                )

            # Trigger re-planning only if scheduling was successful? Or always? Let's do always for now.
            await create_daily_schedule(context.application, chat_id, context)

        except (IndexError, ValueError) as e:
            logger.error(
                f"Error parsing schedule callback time data '{callback_data}': {e}"
            )
            try:
                await query.edit_message_text(
                    text="Ошибка обработки времени подтверждения."
                )
            except Exception as edit_e:
                logger.error(
                    f"Failed to edit message {message_id} for schedule time parse error: {edit_e}"
                )
        except Exception as e:
            logger.error(f"Error scheduling task via callback: {e}", exc_info=True)
            try:
                await query.edit_message_text(
                    text="Произошла ошибка при планировании задачи."
                )
            except Exception as edit_e:
                logger.error(
                    f"Failed to edit message {message_id} for schedule API error: {edit_e}"
                )

    elif action == "skip":
        logger.info(f"User skipped schedule suggestion for task {task_id}")
        task_id_str = str(task_id)
        skipped_set = context.user_data.setdefault("skipped_in_session", set())
        skipped_set.add(task_id_str)
        logger.debug(
            f"Added task {task_id_str} to skipped_in_session. Current list: {skipped_set}"
        )

        skip_msg = await llm_handler.generate_response(
            prompt_type="schedule_skip", data={"task_content": task_content}
        )
        response_text = skip_msg or f"👌 Пропускаем '{task_content}'."

        try:
            await query.edit_message_text(text=response_text)
            logger.debug(f"Edited message {message_id} after skip action.")
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} after skip action: {e}")

        # Trigger re-planning
        await create_daily_schedule(context.application, chat_id, context)

    else:
        logger.warning(f"Unknown callback action: {action}")
        try:
            await query.edit_message_text(text="Неизвестное действие.")
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} for unknown action: {e}")


# --- Setup ---
def setup_telegram_app() -> Application:
    """Sets up and returns the Telegram Application."""
    if not config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in configuration.")

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # --- Remove ConversationHandler ---
    # conv_handler = ConversationHandler(
    #     entry_points=[MessageHandler(filters.TEXT | filters.VOICE & ~filters.COMMAND, handle_message)],
    # application.add_handler(conv_handler)

    # --- Add direct handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    # Handles regular messages (text/voice)
    application.add_handler(
        MessageHandler(filters.TEXT | filters.VOICE & ~filters.COMMAND, handle_message)
    )
    # Handles button presses
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Telegram bot application handlers configured.")
    return application


# ... existing main function ...
