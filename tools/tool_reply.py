import logging
import asyncio
from services.interfaces import (
    ITelegramService,
)  # Зависим только от интерфейса TelegramService
from typing import Optional

logger = logging.getLogger(__name__)


class ReplyToolHandler:
    """
    Обработчик для инструмента 'reply', использующий TelegramService для отправки.
    """

    def __init__(
        self, telegram_service: ITelegramService
    ):  # Remove ConfigService dependency
        self._telegram_service = telegram_service
        logger.debug("ReplyToolHandler initialized with TelegramService.")  # Update log

    def execute(
        self, message: str, user_id: Optional[int] = None
    ) -> dict:  # Re-add user_id parameter
        """
        Пытается отправить сообщение пользователю через TelegramService.
        Если указан user_id, отправляет сообщение напрямую этому пользователю.
        Иначе пытается ответить на текущее сообщение.
        Возвращает статус и флаг об успешности прямой отправки.
        """
        logger.info(
            f"Executing ReplyToolHandler with message: {message[:100]}... and user_id: {user_id}"
        )
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

            if user_id is not None:  # Use passed user_id
                logger.info(f"Attempting to send message to user ID: {user_id}")
                if should_close_loop:
                    # Run directly if we created the loop
                    sent_directly = loop.run_until_complete(
                        self._telegram_service.send_message_to_user(user_id, message)
                    )
                else:
                    # Use run_coroutine_threadsafe if a loop was already running
                    future = asyncio.run_coroutine_threadsafe(
                        self._telegram_service.send_message_to_user(user_id, message),
                        loop,
                    )
                    sent_directly = future.result(
                        timeout=15
                    )  # Use timeout for threadsafe calls
            else:  # Fallback to replying to current message if user_id is None
                logger.info("Attempting to reply to current message.")
                if should_close_loop:
                    # Run directly if we created the loop
                    sent_directly = loop.run_until_complete(
                        self._telegram_service.reply_to_current_message(message)
                    )
                else:
                    # Use run_coroutine_threadsafe if a loop was already running
                    future = asyncio.run_coroutine_threadsafe(
                        self._telegram_service.reply_to_current_message(message), loop
                    )
                    sent_directly = future.result(
                        timeout=15
                    )  # Use timeout for threadsafe calls

            if sent_directly:
                logger.info("Reply sent directly via TelegramService.")
                # Если отправлено, можем не возвращать текст
                final_message = "[Message sent directly]"
            else:
                logger.warning(
                    "TelegramService reported failure to send reply directly."
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
