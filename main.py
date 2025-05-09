import logging
import asyncio
import os

from containers import get_container

# Убираем IRecurringEventsEngine и ILLMService, если они не нужны напрямую здесь
from services.interfaces import (
    IRecurringEventsEngine,
    FileEventData,
)  # Оставляем для stop() and add FileEventData

# Импортируем TelegramAppRunner для аннотации типа
# import telegram_bot # No longer needed for wiring by object

# import message_processor # No longer needed for wiring by object
import recurring_events
from recurring_events import RecurringEventsEngine, DEFAULT_TASKS_DIR_RELATIVE
import tools.utils

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    # level=logging.DEBUG,  # Change logging level to DEBUG
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
            recurring_events,
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
            "recurring_events",  # Already imported as recurring_events
            # "telegram_bot", # Now wired by string name above
        ]
        unique_modules = list(dict.fromkeys(modules_to_wire))  # Remove duplicates
        container.wire(modules=unique_modules)
        logger.info("Modules wired successfully.")
        # --- End Wiring ---

        # Get necessary services
        # Rely on dependency injection wiring for recurring_events
        recurring_engine = container.recurring_events()

        scheduling_service = container.services.scheduling_service()
        vault_service = container.services.vault_service()

        # --- Setup Vault File Watching ---
        vault_root = vault_service.get_vault_root()
        if vault_root:
            tasks_dir = os.path.join(vault_root, DEFAULT_TASKS_DIR_RELATIVE)
            if os.path.isdir(tasks_dir):
                logger.info(
                    f"Setting up watchdog for vault tasks directory: {tasks_dir}"
                )

                def vault_file_event_callback(event_data: FileEventData):
                    """Callback for watchdog file events in the vault tasks directory."""
                    logger.debug(
                        f"Watchdog event in vault tasks dir: {event_data['event_type']} - {event_data['src_path']}"
                    )
                    src_path = event_data["src_path"]
                    # Convert absolute path to relative path within the vault
                    try:
                        # Use os.path.relpath to get the path relative to the vault root
                        relative_path = os.path.relpath(src_path, vault_root)

                        # Ensure the relative path is correctly formatted and within the tasks directory
                        # Check if it starts with the tasks directory name and the separator
                        if (
                            not relative_path.startswith(
                                DEFAULT_TASKS_DIR_RELATIVE + os.sep
                            )
                            and relative_path != DEFAULT_TASKS_DIR_RELATIVE
                        ):
                            # This might happen for events on the tasks directory itself, or files outside it
                            logger.debug(
                                f"Event path {src_path} is not directly within the tasks directory relative to vault root. Relative path: {relative_path}. Skipping."
                            )
                            return

                        # Call the engine's handler for this file event
                        # Get the engine instance from the container inside the callback
                        try:
                            # Use the already retrieved recurring_engine instance
                            recurring_engine.handle_vault_file_event(relative_path)
                        except Exception as e:
                            logger.error(
                                f"Error handling vault file event for {relative_path}: {e}",
                                exc_info=True,
                            )

                    except ValueError as e:
                        logger.error(
                            f"Could not get relative path for {src_path} relative to {vault_root}: {e}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Unexpected error in vault file event callback for {src_path}: {e}",
                            exc_info=True,
                        )

                # Watch the tasks directory BEFORE starting the engine
                scheduling_service.watch_directory(tasks_dir, vault_file_event_callback)
                logger.info("Watchdog setup complete.")
            else:
                logger.warning(
                    f"Vault tasks directory not found at {tasks_dir}. File watching not enabled."
                )
        else:
            logger.warning("Vault root not configured. File watching not enabled.")
        # --- End Vault File Watching Setup ---

        # Start the recurring events engine (which starts the scheduling service including the observer thread)
        logger.info("Starting recurring events engine...")
        recurring_engine.start()

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
