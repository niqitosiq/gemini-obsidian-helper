import logging
import os
import tempfile
import asyncio
from typing import Optional
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telegram.constants import ParseMode
import config
import llm_handler
import scheduler
import knowledge_base

logger = logging.getLogger(__name__)

# States for ConversationHandler (clarifying questions)
ASKING_CLARIFICATION = 1


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
    context.user_data.pop("clarification_state", None)
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels current clarification dialog."""
    user = update.effective_user
    if config.TELEGRAM_USER_ID and user.id != config.TELEGRAM_USER_ID:
        return ConversationHandler.END

    logger.info(f"User {user.id} cancelled the conversation.")
    await update.message.reply_text(
        "Okay, cancelled the current operation.", reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.pop("clarification_state", None)
    return ConversationHandler.END


# --- Message handling ---
async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Optional[int]:
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
        await process_text_input(
            update, context, text_to_analyze, source, conversation_history
        )
        context.user_data["conversation_history"] = conversation_history[-10:]

    return None


async def process_text_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    source: str,
    history: list[str],
):
    """Common text processing logic: analysis, scheduling or clarification."""
    await update.message.reply_chat_action("typing")

    tasks = llm_handler.analyze_text_batch(text, source, history)

    if not tasks:
        await update.message.reply_text(
            "Не удалось проанализировать ваш запрос. Попробуйте переформулировать."
            if any(char in text for char in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
            else "Could not analyze your request. Please try rephrasing."
        )
        return

    # Initialize or clear pending tasks
    context.user_data["pending_tasks"] = []
    first_task_sent = False

    # Process each task sequentially
    for task in tasks:
        source_text = task.get("source_text", text)
        status = task.get("status")

        if status == "complete":
            logger.info(f"Scheduling task: {task.get('action')} (from: {source_text})")
            success, message = scheduler.schedule_task(task, source)
            await update.message.reply_text(message)
        elif status == "incomplete":
            # Add to pending tasks
            context.user_data["pending_tasks"].append(
                {
                    "original_text": source_text,
                    "task": task,
                    "history": history.copy(),
                }
            )

            # If this is the first incomplete task, ask about it right away
            if not first_task_sent:
                question = task.get("clarification_question", "Could you clarify?")
                await update.message.reply_text(
                    f"📝 {task.get('action', 'Task')}: {question}"
                )
                first_task_sent = True
                history.append(f"Assistant: {question}")
                return ASKING_CLARIFICATION

    # If we have pending tasks but haven't sent any questions yet (happens when complete tasks were processed first)
    if context.user_data["pending_tasks"] and not first_task_sent:
        first_task = context.user_data["pending_tasks"][0]["task"]
        question = first_task.get("clarification_question", "Could you clarify?")
        await update.message.reply_text(
            f"📝 {first_task.get('action', 'Task')}: {question}"
        )
        history.append(f"Assistant: {question}")
        return ASKING_CLARIFICATION
    elif not context.user_data["pending_tasks"]:
        # All tasks were complete, clean up
        context.user_data.pop("conversation_history", None)
        context.user_data.pop("pending_tasks", None)
        return ConversationHandler.END

    return ASKING_CLARIFICATION


async def handle_clarification_response(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Optional[int]:
    """Handles user's response in ASKING_CLARIFICATION state."""
    user = update.effective_user
    message = update.message
    logger.info(f"Got clarification response from {user.id}")

    if config.TELEGRAM_USER_ID and user.id != config.TELEGRAM_USER_ID:
        logger.warning(f"Unauthorized user {user.id} in clarification state")
        return ASKING_CLARIFICATION

    pending_tasks = context.user_data.get("pending_tasks", [])
    if not pending_tasks:
        logger.warning("Got response but no pending tasks found. Starting over.")
        await handle_message(update, context)
        return ConversationHandler.END

    response_text = None
    current_task = pending_tasks[0]
    conversation_history = current_task.get("history", [])

    if message.text:
        response_text = message.text
        conversation_history.append(f"User: {response_text}")
        logger.info(f"Text response: {response_text}")
    elif message.voice:
        try:
            voice_file = await message.voice.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_audio:
                await voice_file.download_to_drive(temp_audio.name)
                audio_path = temp_audio.name
            logger.debug(f"Voice response saved to: {audio_path}")
            transcribed_text = llm_handler.transcribe_audio(audio_path)
            try:
                os.remove(audio_path)
            except OSError as e:
                logger.error(f"Error deleting temp audio file {audio_path}: {e}")

            if transcribed_text and "[Transcription Error]" not in transcribed_text:
                response_text = transcribed_text
                conversation_history.append(f"User (Voice): {response_text}")
                await message.reply_text(f'Recognized response: "{response_text}"')
            else:
                await message.reply_text(
                    "❌ Could not recognize response. Please try again with text or voice."
                )
                return ASKING_CLARIFICATION
        except Exception as e:
            logger.error(f"Error processing voice response: {e}", exc_info=True)
            await message.reply_text("Error processing voice response.")
            return ASKING_CLARIFICATION
    else:
        await message.reply_text("Please respond with text or voice.")
        return ASKING_CLARIFICATION

    if response_text:
        # Process the current task with the clarification
        original_text = current_task["original_text"]
        analysis_result = llm_handler.analyze_text_batch(
            f"{original_text} {response_text}",
            "telegram_clarification",
            conversation_history,
        )

        if analysis_result and analysis_result[0].get("status") == "complete":
            # Successfully clarified task, schedule it
            success, message = scheduler.schedule_task(
                analysis_result[0], "telegram_clarification"
            )
            await update.message.reply_text(message)

            # Remove the current task
            pending_tasks.pop(0)
            context.user_data["pending_tasks"] = pending_tasks

            # Process next task if available
            if pending_tasks:
                next_task = pending_tasks[0]["task"]
                question = next_task.get("clarification_question", "Could you clarify?")
                # Add a small delay before asking the next question
                await asyncio.sleep(1)
                await update.message.reply_text(
                    f"📝 {next_task.get('action', 'Task')}: {question}"
                )
                return ASKING_CLARIFICATION
            else:
                # All tasks processed
                context.user_data.pop("pending_tasks", None)
                context.user_data.pop("conversation_history", None)
                return ConversationHandler.END
        else:
            # Still need clarification for current task
            clarification_question = "Could you provide more details?"
            if analysis_result and len(analysis_result) > 0:
                task = analysis_result[0]
                if task.get("clarification_question"):
                    clarification_question = task["clarification_question"]

            await update.message.reply_text(
                f"📝 {current_task['task'].get('action', 'Task')}: {clarification_question}"
            )
            return ASKING_CLARIFICATION

    return ASKING_CLARIFICATION


# --- Error handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs errors and notifies user if possible."""
    logger.error(
        f"Update {update} caused error {context.error}", exc_info=context.error
    )
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "An internal error occurred. I've notified the developers (hopefully)."
                " Please try again later."
            )
        except Exception as e:
            logger.error(f"Could not send error message to user: {e}")


# --- Application setup ---
def setup_telegram_app() -> Application:
    """Creates and configures Telegram Bot application with ConversationHandler."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("Telegram Token not found.")
        raise ValueError("Telegram Token not found.")

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Set default parse mode after building
    application.default_parse_mode = ParseMode.HTML

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.TEXT | filters.VOICE & ~filters.COMMAND, handle_message
            )
        ],
        states={
            ASKING_CLARIFICATION: [
                MessageHandler(
                    filters.TEXT | filters.VOICE & ~filters.COMMAND,
                    handle_clarification_response,
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("start", start_command),
        ],
        conversation_timeout=config.CLARIFICATION_TIMEOUT_SECONDS,
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    logger.info(
        "Telegram application successfully configured with ConversationHandler."
    )
    return application
