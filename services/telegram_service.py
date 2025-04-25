import logging
from typing import Optional
from telegram import Update, constants
from telegram.ext import ContextTypes
from .interfaces import ITelegramService

logger = logging.getLogger(__name__)


class TelegramServiceImpl(ITelegramService):
    """
    Реализация сервиса Telegram для хранения контекста и отправки сообщений.
    Потокобезопасность не гарантируется при активном использовании из разных потоков.
    Предполагается использование в рамках одного запроса/обработчика.
    """

    _current_update: Optional[Update] = None
    _current_context: Optional[ContextTypes.DEFAULT_TYPE] = None

    def __init__(self):
        logger.debug("TelegramService initialized.")

    def set_current_context(
        self, update: Optional[Update], context: Optional[ContextTypes.DEFAULT_TYPE]
    ) -> None:
        """Устанавливает текущий контекст Update/Context."""
        # logger.debug(f"Setting Telegram context: Update={'Yes' if update else 'No'}, Context={'Yes' if context else 'No'}")
        self._current_update = update
        self._current_context = context

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
            logger.error(
                f"Error sending message to user ID {user_id}: {e}", exc_info=True
            )
            return False
