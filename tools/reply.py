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
        await _current_telegram_update.message.reply_markdown(message)
        logger.info(
            f"Message sent to Telegram user {_current_telegram_update.effective_user.id} with Markdown"
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
            # Always try to use the currently running event loop
            try:
                # Get the running event loop if it exists
                loop = asyncio.get_running_loop()
                # Use run_coroutine_threadsafe to submit our coroutine to the loop
                future = asyncio.run_coroutine_threadsafe(
                    _send_telegram_message(message), loop
                )
                # Wait for the result with a timeout
                sent = future.result(timeout=30)  # 30 seconds timeout
                logger.info("Message sent using the existing event loop")
            except RuntimeError:
                # Store the current telegram context values
                temp_update = _current_telegram_update
                temp_context = _current_telegram_context

                # Use a custom approach for when no event loop is running
                # Save the message to be sent by the regular handler
                logger.info(
                    "No running event loop found. Message will be sent by the handler."
                )

                # Signal to the caller that the message should be sent via the regular flow
                sent = False
        except TimeoutError:
            logger.error("Timeout waiting for Telegram message to send (30s).")
            sent = False  # Ensure sent is False on timeout
        except Exception as e:
            # Catch any other exceptions
            logger.error(
                f"Error sending message: {e}",
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
