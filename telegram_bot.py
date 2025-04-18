import logging
import os
import tempfile
import asyncio
from typing import Optional, List, Dict, Any  # Added Dict, Any

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
    CallbackQueryHandler,
)
from telegram.constants import ParseMode
import config
import llm_handler  # Import llm_handler

# import scheduler # Keep if needed for trigger_daily_schedule or fallbacks
import todoist_handler  # Keep for create_task
import knowledge_base

# import semantic_task_manager # Replaced by instruction-based flow
# from update_task_helpers import update_task_duration # Replaced by instruction-based flow
from daily_scheduler import create_daily_schedule  # Keep for trigger_daily_schedule

logger = logging.getLogger(__name__)


# --- Commands (start_command, cancel_command remain mostly the same, but clear new state) ---
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
    # Clear custom states
    context.user_data.pop("pending_question", None)  # NEW state key
    context.user_data.pop("waiting_for_schedule_confirmation", None)  # Keep for now
    context.user_data.pop("skipped_in_session", None)  # Clear skipped list


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancels current clarification or suggestion dialog."""
    user = update.effective_user
    if config.TELEGRAM_USER_ID and user.id != config.TELEGRAM_USER_ID:
        return

    logger.info(f"User {user.id} cancelled the conversation.")
    await update.message.reply_text(
        "Okay, cancelled the current operation.", reply_markup=ReplyKeyboardRemove()
    )
    # Clear custom states
    context.user_data.pop("pending_question", None)  # NEW state key
    context.user_data.pop("waiting_for_schedule_confirmation", None)  # Keep for now
    context.user_data.pop("skipped_in_session", None)  # Clear skipped list


# --- Message handling (handle_message extracts text/voice) ---
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
        # --- REVISED: Call process_text_input which now handles instructions ---
        await process_text_input(
            update, context, text_to_analyze, source, conversation_history
        )
        context.user_data["conversation_history"] = conversation_history[
            -10:
        ]  # Keep history


# --- REVISED process_text_input ---
async def process_text_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    source: str,
    history: list[str],
):
    await update.message.reply_chat_action("typing")
    chat_id = update.effective_chat.id
    logger.debug(f"Processing text input for instructions: '{text}'")

    pending_question_data = context.user_data.pop("pending_question", None)
    pending_key = None
    pending_context = None
    if pending_question_data:
        pending_key = pending_question_data.get("state_key")
        pending_context = pending_question_data.get(
            "context"
        )  # Store any relevant context
        logger.info(f"Processing user response for pending question: {pending_key}")
    else:
        logger.info("Processing new user request.")

    # --- Get Instructions from LLM ---
    try:
        instructions = await llm_handler.get_instructions(
            user_text=text,
            source=source,
            conversation_history=history,
            pending_question_key=pending_key,
            pending_question_context=pending_context,
        )
    except Exception as e:
        logger.error(f"Failed to get instructions from LLM: {e}", exc_info=True)
        await update.message.reply_text(
            "Произошла ошибка при получении инструкций от LLM."
        )
        return  # Stop processing

    if not instructions:
        logger.warning("LLM returned no instructions.")
        # Maybe send a default "I didn't understand" message?
        # For now, just finish.
        return

    # --- Execute Instructions ---
    logger.info(f"Executing {len(instructions)} instructions...")
    for instruction in instructions:
        instruction_type = instruction.get("instruction_type")
        parameters = instruction.get("parameters", {})
        logger.info(
            f"Executing instruction: {instruction_type} with params: {parameters}"
        )

        try:
            if instruction_type == "create_task":
                if not parameters.get("content"):
                    logger.warning("Skipping create_task: missing content.")
                    continue

                # Log before calling
                logger.debug(
                    f"Calling todoist_handler.create_task with params: {parameters}"
                )
                created_task = todoist_handler.create_task(
                    content=parameters.get("content"),
                    description=parameters.get("description"),
                    due_string=parameters.get("due_string"),
                    priority=parameters.get("priority"),
                    project_id=parameters.get("project_id"),
                    duration_minutes=parameters.get("duration_minutes"),
                )
                # Log the result
                if created_task:
                    logger.info(
                        f"todoist_handler.create_task succeeded, created task ID: {created_task.id}"
                    )
                else:
                    logger.error(
                        f"todoist_handler.create_task failed for params: {parameters}"
                    )
                # LLM should generate reply_user instruction for confirmation

            elif instruction_type == "update_task":
                task_id = parameters.get("task_id")
                if not task_id:
                    logger.warning("Skipping update_task: missing task_id.")
                    continue

                update_args = {
                    k: v
                    for k, v in parameters.items()
                    if k != "task_id" and v is not None
                }

                # Handle potential removal logic if needed
                if "due_string" in update_args and update_args["due_string"] == "":
                    pass  # Let handler manage removal
                if (
                    "duration_minutes" in update_args
                    and update_args["duration_minutes"] == 0
                ):
                    update_args["duration_minutes"] = None

                if not update_args:
                    logger.warning(
                        f"Skipping update_task {task_id}: no update parameters provided."
                    )
                    continue

                # --- Add logging for the result ---
                logger.debug(f"Calling todoist_handler.update_task for {task_id}...")
                success = todoist_handler.update_task(task_id=task_id, **update_args)
                logger.info(
                    f"todoist_handler.update_task for {task_id} returned: {success}"
                )  # Log result

                if not success:
                    logger.error(
                        f"Failed to update task {task_id} via instruction (handler returned False): {update_args}"
                    )
                    # Optionally send error reply? Let LLM handle for now.
                else:
                    logger.info(f"Task {task_id} update successful via instruction.")
                    # LLM should generate reply_user instruction for confirmation

            elif instruction_type == "reply_user":
                message_text = parameters.get("message_text")
                if message_text:
                    # --- Add logging after the send attempt ---
                    await update.message.reply_text(message_text)
                    logger.info(
                        f"Sent reply to user: '{message_text[:50]}...'"
                    )  # Log confirmation
                else:
                    logger.warning("Skipping reply_user: missing message_text.")

            # --- Add ask_user logic ---
            elif instruction_type == "ask_user":
                question = parameters.get("question_text")
                state_key = parameters.get("state_key")
                if question and state_key:
                    # Store state for the next message
                    context.user_data["pending_question"] = {
                        "state_key": state_key,
                        # Store related_data as context for the LLM when processing the answer
                        "context": parameters.get("related_data"),
                    }
                    logger.info(
                        f"Asking user question, setting state key: {state_key}. Context: {parameters.get('related_data')}"
                    )
                    await update.message.reply_text(question)
                    # IMPORTANT: Stop processing further instructions after asking
                    return
                else:
                    logger.warning(
                        "Skipping ask_user: missing question_text or state_key."
                    )

            # --- Add finish_request logic ---
            elif instruction_type == "finish_request":
                logger.info(
                    "Finish request instruction received. Clearing pending state."
                )
                # Clear pending state if it wasn't already cleared by a response
                context.user_data.pop("pending_question", None)
                # End processing for this message
                return

            else:
                logger.warning(
                    f"Unknown or unhandled instruction type received: {instruction_type}"
                )

        except Exception as e:
            logger.error(
                f"Error executing instruction {instruction_type}: {e}", exc_info=True
            )
            await update.message.reply_text(
                f"Ошибка при выполнении инструкции: {instruction_type}."
            )
            context.user_data.pop("pending_question", None)  # Clear state on error
            return

    # If loop finishes without finish_request or ask_user, clear state just in case
    context.user_data.pop("pending_question", None)
    logger.debug("Finished processing all instructions for the message.")


# --- Callback Query Handler (button_callback_handler) ---
# This needs review. Schedule confirmation buttons might conflict with the ask_user flow.
# For now, keep it, but prioritize the ask_user/instruction flow.
# If an ask_user is pending, maybe ignore button presses?
async def button_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles button presses for schedule suggestions."""
    query = update.callback_query
    # --- NEW: Check if waiting for text response ---
    if "pending_question" in context.user_data:
        logger.warning("Ignoring button press while waiting for text clarification.")
        try:
            await query.answer("Пожалуйста, сначала ответьте на вопрос текстом.")
        except Exception as e:
            logger.warning(
                f"Failed to answer callback query during pending_question: {e}"
            )
        return

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
