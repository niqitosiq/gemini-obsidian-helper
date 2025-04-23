import logging
import telegram_bot

# Configure logging for the main entry point if needed,
# although telegram_bot already configures basic logging.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting application from main.py...")
    try:
        telegram_bot.main()
    except Exception as e:
        logger.critical(f"Application failed to start or crashed: {e}", exc_info=True)
