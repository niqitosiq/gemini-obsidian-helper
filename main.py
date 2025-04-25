import logging
import asyncio

from containers import get_container

# Убираем IRecurringEventsEngine и ILLMService, если они не нужны напрямую здесь
from services.interfaces import IRecurringEventsEngine  # Оставляем для stop()

# Импортируем TelegramAppRunner для аннотации типа
# import telegram_bot # No longer needed for wiring by object

# import message_processor # No longer needed for wiring by object
import recurring_events_engine
import tools.utils

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main_async():
    """Asynchronous main function to initialize and run all components."""
    global recurring_engine, telegram_runner  # Делаем глобальными для finally
    recurring_engine = None
    telegram_runner = None

    logger.info("Starting application from main.py...")
    try:
        container = get_container()

        # --- Wire modules ---
        # Moved from containers.py to avoid circular import
        logger.info("Wiring modules for dependency injection...")
        modules_to_wire = [
            __name__,  # Import 'main' itself
            "message_processor",  # Use string name for wiring
            "telegram_bot",  # Use string name for wiring
            recurring_events_engine,
            tools.utils,
            "tools.tool_create_file",
            "tools.tool_delete_file",
            "tools.tool_modify_file",
            "tools.tool_create_folder",
            "tools.tool_delete_folder",
            "tools.tool_reply",
            "services.vault_service",
            "services.history_service",
            "services.prompt_builder_service",
            "services.scheduling_service",
            "services.telegram_service",
            "recurring_events_engine",  # Already imported as recurring_events_engine
            # "telegram_bot", # Now wired by string name above
        ]
        unique_modules = list(dict.fromkeys(modules_to_wire))  # Remove duplicates
        container.wire(modules=unique_modules)
        logger.info("Modules wired successfully.")
        # --- End Wiring ---

        config_service = container.core.config_service()
        # LLM сервис инициализируется при первом запросе (например, в TelegramMessageHandler)

        # Получаем и запускаем движок событий
        # Используем провайдер из ApplicationContainer
        recurring_engine = container.recurring_events_engine()
        logger.info("Starting recurring events engine...")
        recurring_engine.start()  # Запускает SchedulingService

        # --- Получаем и запускаем Telegram App Runner ---
        telegram_runner = container.telegram_app_runner()
        logger.info("Starting Telegram application runner...")
        # Запускаем асинхронно (он сам запустит polling)
        await telegram_runner.run()
        # --- Убираем старый прямой запуск ---
        # import telegram_bot
        # await telegram_bot.main_async()

        logger.info("Application running. Press Ctrl+C to stop.")
        # Основной цикл ожидания (можно убрать, если runner блокирует, но start_polling не должен)
        while True:
            await asyncio.sleep(3600)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        # Корректно останавливаем компоненты
        if telegram_runner:
            logger.info("Stopping Telegram runner...")
            await telegram_runner.stop()
        if recurring_engine:
            logger.info("Stopping recurring events engine...")
            recurring_engine.stop()

    except Exception as e:
        logger.critical(f"Application failed to start or crashed: {e}", exc_info=True)
        # Попытка остановить компоненты даже при ошибке
        if telegram_runner:
            try:
                await telegram_runner.stop()
            except Exception as stop_e:
                logger.error(f"Error stopping telegram runner: {stop_e}")
        if recurring_engine:
            try:
                recurring_engine.stop()
            except Exception as stop_e:
                logger.error(f"Error stopping recurring engine: {stop_e}")

    finally:
        logger.info("Application shutdown.")


if __name__ == "__main__":
    asyncio.run(main_async())
