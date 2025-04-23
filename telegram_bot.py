import logging
import os
import uuid  # For unique temporary file names
import asyncio  # Import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Import the specific config variable needed
from config import TELEGRAM_BOT_TOKEN

# Import functions from message_processor
from message_processor import process_user_message, _clear_history_cache

# Import transcription function from llm_handler
import llm_handler

# Import the set_telegram_context function from the reply tool
from tools.reply import set_telegram_context

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Set higher logging level for httpx to avoid GET/POST requests logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! I'm your friendly LLM bot.",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message when the /help command is issued."""
    await update.message.reply_text("Help! I need somebody...")  # Placeholder


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clears the conversation history."""
    logger.info(f"Received /clear command from {update.effective_user.id}")
    try:
        _clear_history_cache()
        await update.message.reply_text("Conversation history cleared.")
        logger.info("Conversation history cleared successfully.")
    except Exception as e:
        logger.error(f"Error clearing history cache: {e}", exc_info=True)
        await update.message.reply_text(
            "Sorry, an error occurred while clearing history."
        )


# --- Message Handlers ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles regular text messages by calling the message processor asynchronously."""
    text = update.message.text
    user_id = update.effective_user.id
    logger.info(f"Received message from {user_id}: {text[:100]}...")

    # Send "typing..." action
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Set Telegram context for the reply tool before processing
    set_telegram_context(update, context)

    # Process the message asynchronously in a separate thread
    try:
        # Use asyncio.to_thread to run the synchronous function without blocking
        result = await asyncio.to_thread(process_user_message, text)
    except Exception as e:
        logger.error(f"Error processing text message: {e}", exc_info=True)
        result = {"error": "An internal error occurred while processing your message."}
    finally:
        # Clear context after processing
        set_telegram_context(None, None)

    # --- Handle the result from the message processor ---
    message_already_sent = False
    reply_message = "Sorry, something went wrong."  # Default error message

    if result:
        # Check if the reply tool handled sending directly
        message_already_sent = result.get("sent_directly", False)

        if message_already_sent:
            logger.info(
                f"Message already sent directly by reply tool to user {user_id}"
            )
        elif "text" in result:  # Plain text response from LLM
            reply_message = result["text"]
        elif (
            "message_to_send" in result
        ):  # Reply tool was used but didn't send (e.g., error)
            reply_message = result.get(
                "message_to_send", "Reply tool used, but no message found."
            )
        elif (
            "status" in result and "message" in result
        ):  # Result from other tools (create_file, etc.)
            status = result.get("status", "unknown")
            message = result.get("message", "Tool executed.")
            # You might want to customize this message format
            reply_message = f"Action Status: {status}\nDetails: {message}"
        elif "error" in result:
            reply_message = f"An error occurred: {result['error']}"
        elif "warning" in result:
            reply_message = f"Note: {result['warning']}"
        # Add more specific checks if process_user_message can return other structures
    else:
        logger.error("process_user_message returned None")
        reply_message = "Sorry, I could not process your request."

    # Only send a message if it wasn't already sent directly
    if not message_already_sent:
        logger.info(f"Replying to {user_id}: {reply_message[:100]}...")
        await update.message.reply_text(reply_message)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles voice messages by transcribing and then processing asynchronously."""
    user_id = update.effective_user.id
    voice = update.message.voice
    logger.info(f"Received voice message from {user_id} (Duration: {voice.duration}s)")

    # Send "typing..." action
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    temp_dir = "temp_audio"
    os.makedirs(temp_dir, exist_ok=True)
    temp_filename = os.path.join(temp_dir, f"{uuid.uuid4()}.oga")
    transcribed_text = None
    result = None

    try:
        # Download the voice file
        voice_file = await voice.get_file()
        await voice_file.download_to_drive(temp_filename)
        logger.info(f"Voice message downloaded to {temp_filename}")

        # Transcribe the audio file (synchronous) - run in thread
        # Assuming transcribe_audio_file is also potentially blocking
        transcribed_text = await asyncio.to_thread(
            llm_handler.transcribe_audio_file, temp_filename
        )

        if transcribed_text is not None:
            logger.info(f"Transcription successful: {transcribed_text[:100]}...")
            # Set Telegram context before processing transcribed text
            set_telegram_context(update, context)
            # Process the transcribed text like a regular message (synchronous) - run in thread
            result = await asyncio.to_thread(process_user_message, transcribed_text)
        else:
            logger.error("Transcription failed.")
            result = {"error": "Sorry, I could not transcribe the audio."}

    except Exception as e:
        logger.error(f"Error handling voice message: {e}", exc_info=True)
        result = {
            "error": "An internal error occurred while processing your voice message."
        }
    finally:
        # Clear context after processing
        set_telegram_context(None, None)
        # Clean up the temporary file
        if os.path.exists(temp_filename):
            try:
                # Run os.remove in a thread as well, as it can block on disk I/O
                await asyncio.to_thread(os.remove, temp_filename)
                logger.info(f"Temporary audio file deleted: {temp_filename}")
            except Exception as e:
                logger.error(
                    f"Error deleting temporary audio file {temp_filename}: {e}"
                )

    # --- Handle the result (same logic as handle_message) ---
    message_already_sent = False
    reply_message = "Sorry, something went wrong."  # Default error message

    if result:
        # Check if the reply tool handled sending directly
        message_already_sent = result.get("sent_directly", False)

        if message_already_sent:
            logger.info(
                f"Message already sent directly by reply tool to user {user_id} (voice)"
            )
        elif "text" in result:  # Plain text response from LLM
            reply_message = result["text"]
        elif "message_to_send" in result:  # Reply tool was used but didn't send
            reply_message = result.get(
                "message_to_send", "Reply tool used, but no message found."
            )
        elif "status" in result and "message" in result:  # Result from other tools
            status = result.get("status", "unknown")
            message = result.get("message", "Tool executed.")
            reply_message = f"Action Status: {status}\nDetails: {message}"
        elif "error" in result:
            reply_message = f"An error occurred: {result['error']}"
        elif "warning" in result:
            reply_message = f"Note: {result['warning']}"
    else:
        logger.error("Processing result was None after handling voice message.")
        reply_message = "Sorry, I could not process your voice message."

    # Only send a message if it wasn't already sent directly
    if not message_already_sent:
        logger.info(f"Replying to {user_id} (voice): {reply_message[:100]}...")
        await update.message.reply_text(reply_message)


# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    # Optionally, notify the user or admin
    # if isinstance(update, Update) and update.effective_message:
    #     await update.effective_message.reply_text("An error occurred. Please try again later.")


# --- Main Bot Logic ---
def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical(
            "TELEGRAM_BOT_TOKEN is not set. Bot cannot start. "
            "Please set the TELEGRAM_BOT_TOKEN environment variable."
        )
        return

    logger.info("Starting bot...")

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))  # Add clear command

    # Register message handler for text messages
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    # Register message handler for voice messages
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Register the error handler
    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is running. Press Ctrl-C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
