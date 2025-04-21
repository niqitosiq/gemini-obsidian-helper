import logging
import os
import tempfile
import asyncio
from typing import Optional, List, Dict, Any
import re
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
import llm_handler
import todoist_handler
import knowledge_base  # Ensure it's imported
from daily_scheduler import create_daily_schedule

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
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming text or voice messages."""
    user = update.effective_user
    message = update.message

    if config.TELEGRAM_USER_ID and user.id != config.TELEGRAM_USER_ID:
        logger.warning(f"Ignored message from unauthorized user {user.id}")
        return None

    text_to_analyze = None
    source = "telegram"  # Default source
    conversation_history = context.user_data.get("conversation_history", [])

    if message.text:
        logger.info(f"Received text message from {user.id}: {message.text}")
        text_to_analyze = message.text
        conversation_history.append(f"User: {text_to_analyze}")
        # --- NEW: Log user text to knowledge base ---
        knowledge_base.log_entry("User", text_to_analyze)

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

            # --- Transcription Call ---
            transcribed_text = await llm_handler.transcribe_audio(voice_file)

            if transcribed_text and "[Transcription Error]" not in transcribed_text:
                text_to_analyze = transcribed_text
                logger.info(f"Voice transcribed for {user.id}: {text_to_analyze}")
                conversation_history.append(f"User: {text_to_analyze} (voice)")
                # --- NEW: Log transcribed voice to knowledge base ---
                knowledge_base.log_entry("User", f"{text_to_analyze} (voice)")
                await message.reply_text(f'Recognized: "{text_to_analyze}"')
            else:
                error_msg = transcribed_text or "Transcription failed."
                logger.error(f"Transcription failed for {user.id}: {error_msg}")
                # --- NEW: Log transcription error ---
                knowledge_base.log_entry(
                    "System", f"Audio transcription failed: {error_msg}"
                )
                await message.reply_text(f"❌ Не удалось распознать аудио: {error_msg}")
        except Exception as e:
            logger.error(f"Error processing voice message: {e}", exc_info=True)
            # --- NEW: Log voice processing error ---
            knowledge_base.log_entry("System", f"Error processing voice message: {e}")
            await message.reply_text(
                "❌ Произошла ошибка при обработке голосового сообщения."
            )
        finally:
            try:
                os.remove(audio_path)
                logger.debug(f"Temporary audio file deleted: {audio_path}")
            except OSError as e:
                logger.error(f"Error deleting temporary audio file {audio_path}: {e}")
    else:
        logger.info(f"Received unsupported message type from {user.id}")
        await message.reply_text("Sorry, I only understand text and voice messages.")
        # --- NEW: Log unsupported type ---
        knowledge_base.log_entry("System", "Received unsupported message type.")
        return None

    if text_to_analyze:
        await process_text_input(
            update, context, text_to_analyze, source, conversation_history
        )
        # Limit history length AFTER processing
        context.user_data["conversation_history"] = conversation_history[
            -10:
        ]  # Keep last 10 turns


# --- REVISED process_text_input ---
async def process_text_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,  # This is the user's *current* input, history is separate
    source: str,
    history: list[str],  # The history already includes the current user message
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
            user_text=text,  # Pass only the current user text here
            source=source,
            conversation_history=history,  # Pass the full history
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
    last_created_task_id: Optional[str] = (
        None  # <-- Track last created task ID for subtasks
    )

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

                # Prepare parameters for todoist_handler
                task_creation_params = {
                    "content": parameters.get("content"),
                    "description": parameters.get("description"),
                    "due_string": parameters.get("due_string"),
                    "priority": parameters.get("priority"),
                    "project_id": parameters.get("project_id"),
                    "duration_minutes": parameters.get("duration_minutes"),
                }

                # --- Add parent_id if it's a subtask and parent exists ---
                is_subtask = parameters.get("is_subtask_of_previous", False)
                if is_subtask and last_created_task_id:
                    task_creation_params["parent_id"] = last_created_task_id
                    logger.info(f"Adding parent_id {last_created_task_id} for subtask.")
                elif is_subtask and not last_created_task_id:
                    logger.warning(
                        "Instruction indicated subtask, but no parent task ID available. Creating as top-level task."
                    )
                # --- End subtask logic ---

                logger.debug(
                    f"Calling todoist_handler.create_task with params: {task_creation_params}"
                )
                created_task = todoist_handler.create_task(**task_creation_params)

                if created_task:
                    logger.info(
                        f"todoist_handler.create_task succeeded, created task ID: {created_task.id}"
                    )
                    last_created_task_id = (
                        created_task.id
                    )  # <-- Store the ID of the created task
                    await asyncio.sleep(2)  # Добавляем задержку 2 секунды
                else:
                    logger.error(
                        f"todoist_handler.create_task failed for params: {task_creation_params}"
                    )
                    last_created_task_id = None  # Reset if creation failed
                # LLM should generate reply_user instruction for confirmation

            elif instruction_type == "update_task":
                last_created_task_id = (
                    None  # Reset parent ID tracking if not creating tasks sequentially
                )
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

                logger.debug(f"Calling todoist_handler.update_task for {task_id}...")
                success = todoist_handler.update_task(task_id=task_id, **update_args)
                logger.info(
                    f"todoist_handler.update_task for {task_id} returned: {success}"
                )
                if success:
                    logger.info(f"Task {task_id} update successful via instruction.")
                    await asyncio.sleep(2)  # Добавляем задержку 2 секунды
                else:
                    logger.error(
                        f"Failed to update task {task_id} via instruction (handler returned False): {update_args}"
                    )
                # LLM should generate reply_user instruction for confirmation

            elif instruction_type == "reply_user":
                # Don't reset last_created_task_id here, confirmation might follow creation
                message_text = parameters.get("message_text")
                if message_text:
                    await update.message.reply_text(message_text)
                    logger.info(f"Sent reply to user: '{message_text[:50]}...'")
                    history.append(f"Assistant: {message_text}")
                    # --- NEW: Log assistant reply ---
                    knowledge_base.log_entry("Assistant", message_text)
                else:
                    logger.warning("Skipping reply_user: missing message_text.")

            # --- MODIFIED: ask_user logic ---
            elif instruction_type == "ask_user":
                last_created_task_id = None  # Reset parent ID tracking
                question = parameters.get("question_text")
                state_key = parameters.get("state_key")
                related_data = parameters.get("related_data")

                if question and state_key:
                    # Store state for the next message or callback
                    context.user_data["pending_question"] = {
                        "state_key": state_key,
                        "context": related_data,  # Store the plan details here
                    }
                    logger.info(
                        f"Asking user question, setting state key: {state_key}. Context: {related_data}"
                    )
                    history.append(f"Assistant: {question}")
                    # --- NEW: Log assistant question ---
                    knowledge_base.log_entry("Assistant", question)

                    # --- NEW: Show buttons for plan confirmation ---
                    if state_key == "confirm_reschedule_plan":
                        keyboard = [
                            [
                                InlineKeyboardButton(
                                    "Подтвердить ✅", callback_data=f"confirm_plan_yes"
                                ),
                                InlineKeyboardButton(
                                    "Отклонить ❌", callback_data=f"confirm_plan_no"
                                ),
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await update.message.reply_text(
                            question, reply_markup=reply_markup
                        )
                    else:
                        # Ask normally without buttons for other clarifications
                        await update.message.reply_text(question)
                    # --- END NEW ---

                    # IMPORTANT: Stop processing further instructions after asking
                    return
                else:
                    logger.warning(
                        "Skipping ask_user: missing question_text or state_key."
                    )

            # --- Add finish_request logic ---
            elif instruction_type == "finish_request":
                last_created_task_id = None  # Reset parent ID tracking
                logger.info(
                    "Finish request instruction received. Clearing pending state."
                )
                # Clear pending state if it wasn't already cleared by a response
                context.user_data.pop("pending_question", None)
                # --- NEW: Log finish action ---
                knowledge_base.log_entry("System", "Request processing finished.")
                # End processing for this message
                return

            else:
                last_created_task_id = (
                    None  # Reset parent ID tracking for unknown types
                )
                logger.warning(
                    f"Unknown or unhandled instruction type received: {instruction_type}"
                )
                # --- NEW: Log unknown instruction ---
                knowledge_base.log_entry(
                    "System", f"Received unknown instruction type: {instruction_type}"
                )

        except Exception as e:
            last_created_task_id = None  # Reset parent ID tracking on error
            logger.error(
                f"Error executing instruction {instruction_type}: {e}", exc_info=True
            )
            await update.message.reply_text(
                f"Ошибка при выполнении инструкции: {instruction_type}."
            )
            context.user_data.pop("pending_question", None)  # Clear state on error
            # --- NEW: Log execution error ---
            knowledge_base.log_entry(
                "System", f"Error executing instruction {instruction_type}: {e}"
            )
            return  # Stop on error

    # If loop finishes without finish_request or ask_user, clear state just in case
    context.user_data.pop("pending_question", None)
    logger.debug("Finished processing all instructions for the message.")


# --- NEW/MODIFIED: Callback Query Handler ---
async def button_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles button presses."""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    user_id = update.effective_user.id
    callback_data = query.data
    logger.info(f"Received button callback from {user_id}: {callback_data}")

    pending_question_data = context.user_data.get("pending_question")

    # --- Handle Plan Confirmation Buttons ---
    if (
        callback_data.startswith("confirm_plan_")
        and pending_question_data
        and pending_question_data.get("state_key") == "confirm_reschedule_plan"
    ):
        # Remove buttons from the original message
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logger.warning(f"Could not edit message reply markup: {e}")

        # Simulate user response ("да" or "нет") to trigger LLM processing
        simulated_user_response = "да" if callback_data == "confirm_plan_yes" else "нет"
        logger.info(
            f"Simulating user response '{simulated_user_response}' for confirm_reschedule_plan"
        )

        conversation_history = context.user_data.get("conversation_history", [])
        # --- MODIFIED: Add simulated user response with prefix ---
        conversation_history.append(f"User: {simulated_user_response} (button press)")

        # Restore pending state temporarily for the call
        context.user_data["pending_question"] = pending_question_data

        await process_text_input(
            update,  # Pass the original update
            context,
            simulated_user_response,  # Pass simulated text
            "telegram_callback",  # Indicate source
            conversation_history,  # Pass updated history
        )
        # Update history in user_data after processing
        context.user_data["conversation_history"] = conversation_history[-10:]

    # --- Handle other potential button callbacks (like the old schedule confirmation) ---
    elif callback_data.startswith("schedule_confirm_") or callback_data.startswith(
        "schedule_skip_"
    ):
        # Keep or adapt the existing logic for the old scheduler buttons if still needed
        # For now, let's just log it
        logger.warning(
            f"Received potentially old scheduler callback: {callback_data}. Ignoring for now."
        )
        await query.message.reply_text("Эта кнопка больше не активна.")  # Inform user

    else:
        logger.warning(f"Unhandled button callback data: {callback_data}")
        await query.message.reply_text("Неизвестное действие кнопки.")


# --- Setup ---
def setup_telegram_app():
    """Sets up and returns the Telegram Application."""
    # --- MODIFIED: Set timeouts directly in the builder ---
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .connect_timeout(100.0)  # Increase connect timeout to 10 seconds
        .read_timeout(200.0)  # Increase read timeout to 20 seconds
        # .write_timeout(10.0) # Can also set write timeout if needed
        # .pool_timeout(10.0)  # Can also set pool timeout if needed
        .build()
    )
    # --- END MODIFIED ---

    # --- Add handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(
        MessageHandler(filters.VOICE & ~filters.COMMAND, handle_message)
    )
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    return application


# ... existing main function ...
