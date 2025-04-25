import logging
import asyncio
from services.interfaces import ITelegramService  # Зависим от интерфейса
from typing import Optional

logger = logging.getLogger(__name__)


class ReplyToolHandler:
    """
    Обработчик для инструмента 'reply', использующий TelegramService для отправки.
    """

    def __init__(self, telegram_service: ITelegramService):
        self._telegram_service = telegram_service
        logger.debug("ReplyToolHandler initialized with TelegramService.")

    def execute(self, message: str, user_id: Optional[int] = None) -> dict:
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
            loop = asyncio.get_running_loop()

            if user_id is not None:
                logger.info(f"Attempting to send message to user ID: {user_id}")
                future = asyncio.run_coroutine_threadsafe(
                    self._telegram_service.send_message_to_user(user_id, message), loop
                )
            else:
                logger.info("Attempting to reply to current message.")
                future = asyncio.run_coroutine_threadsafe(
                    self._telegram_service.reply_to_current_message(message), loop
                )

            # Устанавливаем разумный таймаут, чтобы не блокировать навечно
            sent_directly = future.result(timeout=15)
            if sent_directly:
                logger.info("Reply sent directly via TelegramService.")
                # Если отправлено, можем не возвращать текст
                final_message = "[Message sent directly]"
            else:
                logger.warning(
                    "TelegramService reported failure to send reply directly."
                )

        except RuntimeError:  # Нет активного event loop
            logger.warning(
                "No running event loop found in ReplyToolHandler. Message will be returned for later sending."
            )
            sent_directly = False
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

        return {
            "status": (
                "success" if sent_directly else "pending"
            ),  # pending означает, что надо отправить позже
            "message_to_send": final_message,
            "sent_directly": sent_directly,
        }


# --- Старая функция reply и set_telegram_context УДАЛЕНЫ (если они были здесь) ---
