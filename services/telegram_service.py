import logging
import asyncio
from typing import Optional
import httpx
from telegram import Update, constants
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError as TelegramNetworkError
from .interfaces import ITelegramService

logger = logging.getLogger(__name__)

# Define retry parameters
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1  # seconds
RETRY_BACKOFF_FACTOR = 2 # Delay increases: 1s, 3s, 7s (or adjust factor)
# Or fixed delays: RETRY_DELAYS = [1, 3, 5] # seconds


class TelegramServiceImpl(ITelegramService):
    """
    Реализация сервиса Telegram для хранения контекста и отправки сообщений.
    Потокобезопасность не гарантируется при активном использовании из разных потоков.
    Предполагается использование в рамках одного запроса/обработчика.
    """

    _current_update: Optional[Update] = None
    _current_context: Optional[ContextTypes.DEFAULT_TYPE] = None
    _current_user_id: Optional[int] = None  # Re-add attribute to store user ID

    def __init__(self):
        logger.debug("TelegramService initialized.")

    def set_current_context(
        self, update: Optional[Update], context: Optional[ContextTypes.DEFAULT_TYPE]
    ) -> None:
        """Устанавливает текущий контекст Update/Context и ID пользователя."""
        # logger.debug(f"Setting Telegram context: Update={'Yes' if update else 'No'}, Context={'Yes' if context else 'No'}")
        self._current_update = update
        self._current_context = context
        # Re-add logic to store the user ID if available
        self._current_user_id = (
            update.effective_user.id if update and update.effective_user else None
        )
        logger.debug(f"Set current user ID in TelegramService: {self._current_user_id}")

    def get_current_user_id(self) -> Optional[int]:
        """Возвращает ID текущего пользователя из контекста."""
        return self._current_user_id

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = constants.ParseMode.MARKDOWN,
    ) -> bool:
        """Отправляет сообщение в указанный чат."""
        if not self._current_context or not self._current_context.bot:
            logger.error(
                "Cannot send message: Telegram context or bot is not available."
            )
            return False
        try:
            await self._current_context.bot.send_message(
                chat_id=chat_id, text=text, parse_mode=parse_mode
            )
            logger.debug(f"Message sent to chat_id {chat_id}.")
            return True
        except Exception as e:
            logger.error(
                f"Error sending message to chat_id {chat_id}: {e}", exc_info=True
            )
            return False

    async def reply_to_current_message(
        self, text: str, parse_mode: Optional[str] = constants.ParseMode.MARKDOWN
    ) -> bool:
        """Отправляет сообщение в ответ на текущее обрабатываемое сообщение."""
        if not self._current_update or not self._current_update.effective_message:
            logger.error(
                "Cannot reply to message: Telegram update or message is not available in context."
            )
            return False
        try:
            await self._current_update.effective_message.reply_text(
                text=text, parse_mode=parse_mode
            )
            logger.info(
                f"Replied to user {self._current_update.effective_user.id if self._current_update.effective_user else 'Unknown'} in chat {self._current_update.effective_chat.id if self._current_update.effective_chat else 'Unknown'}"
            )
            return True
        except Exception as e:
            logger.error(f"Error replying to message: {e}", exc_info=True)
            return False

    async def send_message_to_user(
        self,
        user_id: int,
        text: str,
        parse_mode: Optional[str] = constants.ParseMode.MARKDOWN,
    ) -> bool:
        """Отправляет сообщение указанному пользователю по его ID."""
        if not self._current_context or not self._current_context.bot:
            logger.error(
                "Cannot send message to user: Telegram context or bot is not available."
            )
            return False
        try:
            await self._current_context.bot.send_message(
                chat_id=user_id, text=text, parse_mode=parse_mode
            )
            logger.info(f"Message sent to user ID {user_id}.")
            return True
        except Exception as e:
            logger.info(f"Message sent to user ID {user_id}.")
            return True
        except (TimedOut, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError, TelegramNetworkError) as e:
            logger.warning(f"Attempt 1: Failed to send message to user ID {user_id} due to network/timeout error: {e}. Retrying...")
            current_delay = INITIAL_RETRY_DELAY
            for attempt in range(2, MAX_RETRIES + 2): # Start from attempt 2 up to MAX_RETRIES+1
                await asyncio.sleep(current_delay)
                try:
                    await self._current_context.bot.send_message(
                        chat_id=user_id, text=text, parse_mode=parse_mode
                    )
                    logger.info(f"Message sent successfully to user ID {user_id} on attempt {attempt}.")
                    return True
                except (TimedOut, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError, TelegramNetworkError) as retry_e:
                    if attempt > MAX_RETRIES:
                         logger.error(
                            f"Final attempt ({attempt-1}) failed. Error sending message to user ID {user_id} after {MAX_RETRIES} retries: {retry_e}",
                            exc_info=True,
                        )
                         return False
                    else:
                        logger.warning(
                            f"Attempt {attempt}: Failed to send message to user ID {user_id}: {retry_e}. Retrying in {current_delay * RETRY_BACKOFF_FACTOR}s..."
                        )
                        current_delay *= RETRY_BACKOFF_FACTOR # Exponential backoff
                        # Or use fixed delays: current_delay = RETRY_DELAYS[attempt-1] if attempt-1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]

                except Exception as final_e: # Catch other unexpected errors during retry
                    logger.error(
                        f"Unexpected error sending message to user ID {user_id} during retry attempt {attempt}: {final_e}",
                        exc_info=True,
                    )
                    return False

        except Exception as e: # Catch other non-retryable exceptions on the first try
            logger.error(
                f"Non-retryable error sending message to user ID {user_id}: {e}", exc_info=True
            )
            return False
