import logging
import asyncio
import os
from dotenv import load_dotenv
from services.interfaces import (
    ITelegramService,
)
from typing import Optional

logger = logging.getLogger(__name__)

# Load .env file to access environment variables directly if needed
load_dotenv()
PRIMARY_USER_ID_FROM_ENV = os.getenv("TELEGRAM_USER_ID")
if PRIMARY_USER_ID_FROM_ENV:
    try:
        # Assume comma-separated, take the first one
        PRIMARY_USER_ID_INT = int(PRIMARY_USER_ID_FROM_ENV.split(",")[0].strip())
        logger.info(
            f"Primary User ID loaded from TELEGRAM_USER_ID env var: {PRIMARY_USER_ID_INT}"
        )
    except (ValueError, IndexError):
        logger.error(
            f"Could not parse TELEGRAM_USER_ID from env var: '{PRIMARY_USER_ID_FROM_ENV}'. Fallback will fail."
        )
        PRIMARY_USER_ID_INT = None
else:
    logger.warning(
        "TELEGRAM_USER_ID environment variable not found. Reply tool fallback will fail."
    )
    PRIMARY_USER_ID_INT = None


class ReplyToolHandler:
    """
    Обработчик для инструмента 'reply', использующий TelegramService для отправки.
    """

    def __init__(
        self, telegram_service: ITelegramService
    ):  # Remove ConfigService dependency
        self._telegram_service = telegram_service
        logger.debug("ReplyToolHandler initialized with TelegramService.")

    def execute(self, message: str, user_id: Optional[int] = None) -> dict:
        """
        Отправляет сообщение указанному пользователю через TelegramService.
        Если user_id не предоставлен, пытается использовать ID из переменной окружения TELEGRAM_USER_ID.
        Возвращает статус и флаг об успешности прямой отправки.
        """
        logger.info(
            f"Executing ReplyToolHandler with message: {message[:100]}... and provided user_id: {user_id}"
        )

        target_user_id = user_id

        if target_user_id is None:
            logger.warning(
                "user_id not provided to ReplyToolHandler. Attempting fallback to primary user ID from environment."
            )
            target_user_id = PRIMARY_USER_ID_INT  # Use the ID loaded at module start

        if target_user_id is None:
            logger.error(
                "ReplyToolHandler requires a user_id, and fallback from environment failed or was not available."
            )
            return {
                "status": "failed",
                "message_to_send": "Error: user_id not provided and fallback failed.",
                "sent_directly": False,
            }

        # Ensure target_user_id is an integer before proceeding
        try:
            target_user_id = int(target_user_id)
        except (ValueError, TypeError):
            logger.error(
                f"Failed to convert target_user_id '{target_user_id}' to integer."
            )
            return {
                "status": "failed",
                "message_to_send": f"Error: Invalid target_user_id '{target_user_id}'.",
                "sent_directly": False,
            }

        sent_directly = False
        final_message = message  # Сообщение, которое вернем, если отправка не удалась

        try:
            loop = None
            try:
                loop = asyncio.get_running_loop()
                logger.debug("Found running event loop.")
            except RuntimeError:
                logger.warning(
                    "No running event loop found. Creating a new one temporarily."
                )
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                should_close_loop = True
            else:
                should_close_loop = False

            # Always use send_message_to_user with the resolved target_user_id
            logger.info(
                f"Attempting to send message to target user ID: {target_user_id}"
            )
            if should_close_loop:
                # Run directly if we created the loop
                sent_directly = loop.run_until_complete(
                    self._telegram_service.send_message_to_user(target_user_id, message)
                )
            else:
                # Use run_coroutine_threadsafe if a loop was already running
                future = asyncio.run_coroutine_threadsafe(
                    self._telegram_service.send_message_to_user(
                        target_user_id, message
                    ),
                    loop,
                )
                sent_directly = future.result(
                    timeout=15
                )  # Use timeout for threadsafe calls

            if sent_directly:
                logger.info(
                    f"Message sent directly to user {target_user_id} via TelegramService."
                )
                # Если отправлено, можем не возвращать текст
                final_message = "[Message sent directly]"
            else:
                # This warning might still occur if send_message_to_user fails
                logger.warning(
                    f"TelegramService reported failure sending message to user {target_user_id}."
                )

        except TimeoutError:
            logger.error(
                "Timeout waiting for Telegram message to send via ReplyToolHandler."
            )
            sent_directly = False
        except Exception as e:
            logger.error(
                f"Error trying to send reply via TelegramService: {e}",
                exc_info=True,
            )
            sent_directly = False
        finally:
            # Ensure the created loop is closed
            if (
                "should_close_loop" in locals()
                and should_close_loop
                and loop
                and loop.is_running()
            ):
                loop.stop()
                loop.close()
                logger.debug("Closed temporarily created event loop.")
                asyncio.set_event_loop(None)  # Clean up the event loop policy

        return {
            "status": (
                "success" if sent_directly else "pending"
            ),  # pending означает, что надо отправить позже
            "message_to_send": final_message,
            "sent_directly": sent_directly,
        }


# --- Старая функция reply и set_telegram_context УДАЛЕНЫ (если они были здесь) ---
