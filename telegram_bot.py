import logging
import os
import uuid
import asyncio
from typing import Optional, Dict, Any

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    Defaults,
)
from telegram.constants import ParseMode

# --- DI ---
from dependency_injector.wiring import inject, Provide

# from containers import ApplicationContainer # Removed to break circular import

# --- Интерфейсы и Сервисы ---
from services.interfaces import (
    IConfigService,
    ILLMService,
    IHistoryService,
    ITelegramService,
    IVaultService,  # Add VaultService
    IPromptBuilderService,  # Add PromptBuilderService
)
from dependency_injector import providers  # For tool_handlers_map type hint

# Импортируем основную функцию обработки (которую будем вызывать)
# Она больше НЕ будет DI-aware, зависимости передадим явно
from message_processor import process_user_message

logger = logging.getLogger(__name__)


# --- Вспомогательная функция обработки ошибок ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логгирует ошибки, вызванные Update."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    # Можно добавить отправку сообщения пользователю или админу
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Произошла внутренняя ошибка. Пожалуйста, попробуйте позже."
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")


# --- Основной Обработчик Сообщений Telegram ---
class TelegramMessageHandler:
    """Обрабатывает входящие сообщения и команды Telegram."""

    # @inject decorator removed - dependencies are passed via constructor injection
    def __init__(
        self,
        # Dependencies are now passed directly by the container
        llm_service: ILLMService,
        telegram_service: ITelegramService,
        history_service: IHistoryService,
        vault_service: IVaultService,
        prompt_builder_service: IPromptBuilderService,
        tool_handlers_map_provider: dict,  # Type hint updated to dict
    ):
        self._llm_service = llm_service
        self._telegram_service = telegram_service
        self._history_service = history_service
        self._vault_service = vault_service
        self._prompt_builder_service = prompt_builder_service
        self._tool_handlers_map_provider = (
            tool_handlers_map_provider  # Store the provider
        )
        logger.debug("TelegramMessageHandler initialized.")

    async def _process_and_reply(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str
    ):
        """Общая логика обработки текста и отправки ответа."""
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        chat_id = update.effective_chat.id if update.effective_chat else "Unknown"
        logger.info(
            f"Processing message from user {user_id} in chat {chat_id}: {message_text[:100]}..."
        )

        # Устанавливаем контекст для TelegramService (важно для ReplyToolHandler)
        self._telegram_service.set_current_context(update, context)

        # Отправляем "typing..."
        if context.bot and chat_id != "Unknown":
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception as e:
                logger.warning(f"Failed to send typing action: {e}")

        final_reply_message = None
        message_sent_directly = False

        try:
            # Вызываем функцию обработки сообщения, передавая зависимости ЯВНО
            # Use the injected dictionary directly
            tool_handlers_map = self._tool_handlers_map_provider
            result = await asyncio.to_thread(
                process_user_message,
                message_text,
                history_service=self._history_service,
                llm_service=self._llm_service,
                vault_service=self._vault_service,
                prompt_builder=self._prompt_builder_service,
                tool_handlers_map=tool_handlers_map,
                user_id=user_id,  # Pass the user_id
            )

            # Обрабатываем результат
            if result:
                message_sent_directly = result.get("sent_directly", False)
                if message_sent_directly:
                    logger.info(
                        "Message was sent directly by a tool handler (e.g., reply). No further action needed."
                    )
                    final_reply_message = None  # Не отправляем ничего дополнительно
                elif "text" in result:
                    final_reply_message = result["text"]
                elif (
                    "message_to_send" in result
                ):  # Если reply не смог отправить напрямую
                    final_reply_message = result["message_to_send"]
                elif "error" in result:
                    final_reply_message = f"Ошибка: {result['error']}"
                elif "warning" in result:
                    final_reply_message = f"Предупреждение: {result['warning']}"
                # Можно добавить обработку статусов success от других инструментов
                elif "status" in result and "message" in result:
                    final_reply_message = (
                        f"Статус: {result['status']}. {result['message']}"
                    )

        except Exception as e:
            logger.error(
                f"Error processing message via process_user_message: {e}", exc_info=True
            )
            final_reply_message = "Произошла серьезная внутренняя ошибка."
        # finally: # Moved context reset to after message sending attempt
        # # Сбрасываем контекст после обработки
        # self._telegram_service.set_current_context(None, None)

        # Отправляем ответ, если он есть и не был отправлен напрямую
        if final_reply_message and chat_id != "Unknown":
            logger.info(f"Replying to user {user_id}: {final_reply_message[:100]}...")
            # Используем send_message из TelegramService, чтобы не зависеть от context.bot напрямую здесь
            await self._telegram_service.send_message(chat_id, final_reply_message)

        # Сбрасываем контекст после обработки и попытки отправки ответа
        # self._telegram_service.set_current_context(None, None)

    # --- Обработчики для telegram.ext ---
    async def text_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обработчик текстовых сообщений."""
        if not update.message or not update.message.text:
            return
        await self._process_and_reply(update, context, update.message.text)

    async def voice_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обработчик голосовых сообщений."""
        if not update.message or not update.message.voice:
            return

        user_id = update.effective_user.id if update.effective_user else "Unknown"
        voice = update.message.voice
        logger.info(
            f"Received voice message from {user_id} (Duration: {voice.duration}s)"
        )

        # Устанавливаем контекст (для возможной отправки ошибок)
        self._telegram_service.set_current_context(update, context)

        temp_dir = "temp_audio"  # Можно вынести в конфиг
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = os.path.join(temp_dir, f"{uuid.uuid4()}.oga")
        transcribed_text: Optional[str] = None

        try:
            # Отправляем "typing..."
            if context.bot and update.effective_chat:
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id, action="typing"
                )

            # Скачиваем файл
            voice_file = await voice.get_file()
            await voice_file.download_to_drive(temp_filename)
            logger.info(f"Voice message downloaded to {temp_filename}")

            # Транскрибируем через LLMService (запускаем в потоке, т.к. сервис синхронный)
            logger.info("Starting audio transcription...")
            transcribed_text = await asyncio.to_thread(
                self._llm_service.transcribe_audio, temp_filename
            )

        except Exception as e:
            logger.error(
                f"Error downloading or transcribing voice message: {e}", exc_info=True
            )
            # Используем reply_to_current_message из TelegramService
            await self._telegram_service.reply_to_current_message(
                "Ошибка при обработке голосового сообщения."
            )
            transcribed_text = None  # Убедимся, что текст None
        finally:
            # Удаляем временный файл в потоке
            if os.path.exists(temp_filename):
                try:
                    await asyncio.to_thread(os.remove, temp_filename)
                    logger.info(f"Temporary audio file deleted: {temp_filename}")
                except Exception as e_del:
                    logger.error(
                        f"Error deleting temporary audio file {temp_filename}: {e_del}"
                    )
            # Сбрасываем контекст только если не передаем дальше
            # self._telegram_service.set_current_context(None, None) # Не сбрасываем, т.к. вызываем _process_and_reply

        # Если транскрипция успешна, обрабатываем как текстовое сообщение
        if transcribed_text is not None:
            logger.info(f"Transcription successful: {transcribed_text[:100]}...")
            # Контекст уже установлен, вызываем обработку
            await self._process_and_reply(update, context, transcribed_text)
        else:
            logger.error("Transcription failed, no text to process.")
            # Сообщение об ошибке уже должно было быть отправлено
            # Сбрасываем контекст, т.к. обработка завершена (неудачно)
            # self._telegram_service.set_current_context(None, None)

    async def start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обработчик команды /start."""
        user = update.effective_user
        message = (
            rf"Привет, {user.mention_html()}! 👋 Я твой ИИ ассистент. Чем могу помочь?"
        )
        if update.message:
            await update.message.reply_html(message)

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обработчик команды /help."""
        message = (
            "Я могу помочь тебе управлять задачами и заметками в Obsidian. "
            "Просто напиши мне, что нужно сделать.\n\n"
            "Доступные команды:\n"
            "/start - Приветствие\n"
            "/clear - Очистить историю диалога\n"
            "/help - Показать это сообщение"
        )
        if update.message:
            await update.message.reply_text(message)

    async def clear_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обработчик команды /clear."""
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        logger.info(f"Received /clear command from {user_id}")
        try:
            # Используем history_service из DI
            self._history_service.clear_history()
            logger.info("Conversation history cleared successfully via HistoryService.")
            if update.message:
                await update.message.reply_text("История диалога очищена. ✨")
        except Exception as e:
            logger.error(
                f"Error clearing history via HistoryService: {e}", exc_info=True
            )
            if update.message:
                await update.message.reply_text(
                    "Не удалось очистить историю. Попробуйте позже."
                )


# --- Компонент Запуска Приложения Telegram ---
class TelegramAppRunner:
    """Настраивает и запускает приложение python-telegram-bot."""

    @inject
    def __init__(
        self,
        # Use string paths for Provide to avoid circular import
        config_service: IConfigService = Provide[
            "ApplicationContainer.core.config_service"
        ],
        message_handler_instance: TelegramMessageHandler = Provide[
            "ApplicationContainer.telegram_message_handler"
        ],  # Зависим от обработчика
    ):
        self._config_service = config_service
        self._message_handler = message_handler_instance
        self._application: Optional[Application] = None
        logger.debug("TelegramAppRunner initialized.")

    async def run(self):
        """Инициализирует и запускает бота в режиме polling."""
        bot_token = self._config_service.get_telegram_bot_token()
        if not bot_token:
            logger.critical("TELEGRAM_BOT_TOKEN is not configured. Bot cannot start.")
            return

        logger.info("Starting Telegram bot application runner...")

        # Установка настроек по умолчанию (например, parse_mode)
        defaults = Defaults(parse_mode=ParseMode.MARKDOWN)

        # Сборка приложения
        self._application = (
            ApplicationBuilder().token(bot_token).defaults(defaults).build()
        )

        # Регистрация обработчиков
        self._application.add_handler(
            CommandHandler("start", self._message_handler.start_command)
        )
        self._application.add_handler(
            CommandHandler("help", self._message_handler.help_command)
        )
        self._application.add_handler(
            CommandHandler("clear", self._message_handler.clear_command)
        )
        self._application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, self._message_handler.text_handler
            )
        )
        self._application.add_handler(
            MessageHandler(filters.VOICE, self._message_handler.voice_handler)
        )

        # Регистрация обработчика ошибок
        self._application.add_error_handler(error_handler)  # Используем простую функцию

        # Запуск в режиме polling (асинхронно)
        try:
            await self._application.initialize()
            await self._application.start()
            # Используем start_polling вместо run_polling, чтобы не блокировать main.py
            await self._application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES
            )
            logger.info("Telegram bot application started polling.")

            # Приложение теперь работает в фоне, можно добавить ожидание, если нужно
            # while True: await asyncio.sleep(3600) # Это ожидание теперь в main.py

        except Exception as e:
            logger.critical(f"Failed to start Telegram bot polling: {e}", exc_info=True)

    async def stop(self):
        """Останавливает приложение Telegram."""
        if self._application and self._application.updater:
            logger.info("Stopping Telegram bot application...")
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()
            logger.info("Telegram bot application stopped.")
        else:
            logger.warning(
                "Telegram application or updater not available for stopping."
            )


# --- Старые функции main, main_async УДАЛЕНЫ ---
