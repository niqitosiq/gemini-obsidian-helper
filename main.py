import logging
import asyncio
import time
from datetime import datetime
import config  # Import config first for .env loading
from utils import setup_logging
import telegram_bot
import daily_scheduler

# Set up logging at startup
setup_logging()
logger = logging.getLogger(__name__)


async def schedule_morning_reminders(tg_app):
    """Run the morning schedule creation on a daily basis."""
    logger.info("Starting morning schedule reminder service")

    while True:
        now = datetime.now()
        # Set time for morning schedule creation (8:00 AM)
        target_hour = (
            config.MORNING_SCHEDULE_HOUR
            if hasattr(config, "MORNING_SCHEDULE_HOUR")
            else 8
        )

        # Calculate time until next schedule creation
        if now.hour < target_hour:
            # Schedule for today
            next_run = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        else:
            # Schedule for tomorrow
            from datetime import timedelta

            next_run = now.replace(
                hour=target_hour, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)

        # Sleep until the next scheduled time
        sleep_seconds = (next_run - now).total_seconds()
        logger.info(f"Next morning schedule will run in {sleep_seconds/3600:.1f} hours")

        # Add a small extra delay to ensure we're past the target time
        # when we wake up (avoiding potential edge cases)
        sleep_seconds += 1

        try:
            await asyncio.sleep(sleep_seconds)

            # Create and send the daily schedule
            logger.info("Creating daily schedule")
            await daily_scheduler.create_daily_schedule(tg_app)

        except asyncio.CancelledError:
            logger.info("Morning schedule service cancelled")
            break
        except Exception as e:
            logger.error(f"Error in morning schedule service: {e}", exc_info=True)
            # Wait a bit before retrying after an error
            await asyncio.sleep(300)


async def main_async() -> None:
    """Async version of main to support scheduling tasks."""
    logger.info("Starting Personal Assistant Bot...")

    try:
        logger.info("Initializing Telegram application...")
        tg_app = telegram_bot.setup_telegram_app()

        # Start the morning schedule service
        morning_schedule_task = asyncio.create_task(schedule_morning_reminders(tg_app))

        # Start the bot
        logger.info("Starting Telegram Bot polling...")
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling()

        # Keep the bot running until interrupted
        # Use idle instead of stop_on_exception which doesn't exist
        await asyncio.Future()  # This will wait indefinitely

    except Exception as e:
        logger.critical(f"Critical error starting Telegram bot: {e}", exc_info=True)
    finally:
        logger.info("Bot operation complete.")


def main() -> None:
    """Starts bot and other components."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Bot manually interrupted")
    except Exception as e:
        logger.critical(f"Unhandled error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
