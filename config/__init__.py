import os
import logging
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
# Useful for local development.
load_dotenv()

logger = logging.getLogger(__name__)

# --- API Keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Model Settings ---
# Add the model name configuration
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_USER_ID = os.getenv(
    "TELEGRAM_USER_ID"
)  # Can be comma-separated for multiple users

# --- Obsidian Settings ---
OBSIDIAN_DAILY_NOTES_FOLDER = os.getenv("OBSIDIAN_DAILY_NOTES_FOLDER")
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH")  # Add vault path


# --- Application Settings ---
# Example: Add other settings as needed
# LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Validations ---
if not GEMINI_API_KEY:
    logger.warning(
        "GEMINI_API_KEY environment variable not set. LLM functionality will be disabled."
    )

if not TELEGRAM_BOT_TOKEN:
    logger.warning(
        "TELEGRAM_BOT_TOKEN environment variable not set. Telegram bot functionality may be disabled."
    )

if not TELEGRAM_USER_ID:
    logger.warning(
        "TELEGRAM_USER_ID environment variable not set. Telegram bot may not restrict users."
    )

if not OBSIDIAN_DAILY_NOTES_FOLDER:
    logger.warning(
        "OBSIDIAN_DAILY_NOTES_FOLDER environment variable not set. Obsidian integration may be disabled."
    )

if not OBSIDIAN_VAULT_PATH:  # Add validation for vault path
    logger.warning(
        "OBSIDIAN_VAULT_PATH environment variable not set. Obsidian integration may be disabled or use a default path."
    )


# You can add more configuration variables and validations below
