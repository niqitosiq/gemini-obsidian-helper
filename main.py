import logging
import asyncio
import telegram_bot
from recurring_events_engine import get_engine

# Configure logging for the main entry point if needed,
# although telegram_bot already configures basic logging.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main_async():
    """Asynchronous main function to initialize and run all components."""
    logger.info("Starting application from main.py...")
    try:
        # Initialize and start the recurring events engine
        logger.info("Starting recurring events engine...")
        recurring_engine = get_engine()
        recurring_engine.start()

        # Start the telegram bot
        logger.info("Starting telegram bot...")
        await telegram_bot.main_async()

        # Keep the application running
        logger.info("Application running. Press Ctrl+C to stop.")
        # Use an infinite loop with a sleep to prevent the function from exiting
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour and continue the loop
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.critical(f"Application failed to start or crashed: {e}", exc_info=True)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main_async())
