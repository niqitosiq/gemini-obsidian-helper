import logging
from telegram.ext import ContextTypes
from telegram import Update
import asyncio  # Import asyncio

logger = logging.getLogger(__name__)

# A global variable to store the current update and context
_current_telegram_update = None
_current_telegram_context = None


def set_telegram_context(
    update: Update = None, context: ContextTypes.DEFAULT_TYPE = None
):
    """Set the current Telegram update and context objects for the reply tool."""
    global _current_telegram_update, _current_telegram_context
    _current_telegram_update = update
    _current_telegram_context = context
    logger.debug("Telegram context set for reply tool")


async def _send_telegram_message(message: str) -> bool:
    """Helper function to send a message to the current Telegram chat."""
    global _current_telegram_update, _current_telegram_context

    if not _current_telegram_update or not _current_telegram_context:
        logger.error("Cannot send Telegram message: No active context")
        return False

    try:
        await _current_telegram_update.message.reply_text(message)
        logger.info(
            f"Message sent to Telegram user {_current_telegram_update.effective_user.id}"
        )
        return True
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}", exc_info=True)
        return False


def reply(message: str) -> dict:
    """
    Reply tool function that directly sends the message to the Telegram user.

    The function uses the stored Telegram context to send the message immediately,
    rather than returning the message to be sent by the handler. It handles
    being called from a synchronous context while needing to run an async function.
    """
    logger.info(f"Tool 'reply' called with message: {message[:100]}...")

    sent = False
    future = None

    # If we have a context, try to send the message directly
    if _current_telegram_update and _current_telegram_context:
        try:
            # Get the currently running event loop
            loop = asyncio.get_running_loop()
            # Submit the coroutine to the loop from this synchronous thread
            future = asyncio.run_coroutine_threadsafe(
                _send_telegram_message(message), loop
            )
            # Wait for the result (with a longer timeout)
            # Adjust timeout as needed
            sent = future.result(timeout=30)  # Increased timeout to 30 seconds
        except RuntimeError as e:
            # This might happen if there's no running loop (e.g., testing outside bot context)
            logger.error(
                f"Could not get running event loop: {e}. Message not sent directly."
            )
            sent = False  # Ensure sent is False if loop isn't running
        except TimeoutError:
            logger.error(
                "Timeout waiting for Telegram message to send (30s)."
            )  # Updated log message
            sent = False  # Ensure sent is False on timeout
        except Exception as e:
            # Catch other potential exceptions from result() or run_coroutine_threadsafe
            logger.error(
                f"Error sending message via run_coroutine_threadsafe: {e}",
                exc_info=True,
            )
            sent = False  # Ensure sent is False on other errors

    # If direct sending failed or wasn't possible, still return the message
    # This allows the normal flow to still work as fallback
    return {
        "status": "success" if sent else "handled_by_processor",
        "message_to_send": message,
        "sent_directly": sent,
    }
