import logging
import config  # Import config first for .env loading
from utils import setup_logging
import telegram_bot

# Set up logging at startup
setup_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    """Starts bot and other components."""
    logger.info("Starting Personal Assistant Bot...")

    # --- Initialize and start Telegram bot ---
    try:
        logger.info("Initializing Telegram application...")
        tg_app = telegram_bot.setup_telegram_app()
        logger.info("Starting Telegram Bot polling...")
        # run_polling() is blocking, will run until bot is stopped
        tg_app.run_polling()
    except Exception as e:
        logger.critical(f"Critical error starting Telegram bot: {e}", exc_info=True)

    # --- Initialize other listeners (later) ---
    # logger.info("Initializing Slack Listener...")
    # setup_slack_listener()

    # logger.info("Initializing Jira Listener...")
    # setup_jira_listener()

    logger.info("Bot operation complete.")  # Will only reach here when polling stops


if __name__ == "__main__":
    main()
