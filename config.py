import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# API Keys
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TODOIST_API_TOKEN = os.getenv("TODOIST_API_TOKEN")

# User IDs
_telegram_user_id_str = os.getenv("TELEGRAM_USER_ID")
TELEGRAM_USER_ID = (
    int(_telegram_user_id_str)
    if _telegram_user_id_str and _telegram_user_id_str.isdigit()
    else None
)

# Settings
WORK_START_HOUR = int(os.getenv("WORK_START_HOUR", 9))
WORK_END_HOUR = int(os.getenv("WORK_END_HOUR", 18))
_work_days_str = os.getenv("WORK_DAYS", "1,2,3,4,5")
WORK_DAYS = [
    int(day.strip()) for day in _work_days_str.split(",") if day.strip().isdigit()
]  # 1=Mon, 7=Sun
GEMINI_CONTEXT_LEVEL = os.getenv("GEMINI_CONTEXT_LEVEL", "maximal")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
CLARIFICATION_TIMEOUT_SECONDS = int(
    os.getenv("CLARIFICATION_TIMEOUT_SECONDS", 300)
)  # 5 minutes

# --- Knowledge Base Settings ---
KNOWLEDGE_BASE_ENABLED = True
KNOWLEDGE_BASE_FILE = "knowledge_base.md"

# --- Obsidian Configuration ---
OBSIDIAN_VAULT_PATH = "/path/to/your/actual/obsidian/vault"  # IMPORTANT: Replace with your real vault path

# Validation of critical configurations
if not TELEGRAM_BOT_TOKEN:
    logger.critical("Critical error: TELEGRAM_BOT_TOKEN not found in configuration!")
    raise ValueError("TELEGRAM_BOT_TOKEN not found")
if not GEMINI_API_KEY:
    logger.critical("Critical error: GEMINI_API_KEY not found in configuration!")
    raise ValueError("GEMINI_API_KEY not found")
if not TODOIST_API_TOKEN:
    logger.critical("Critical error: TODOIST_API_TOKEN not found in configuration!")
    raise ValueError("TODOIST_API_TOKEN not found")
if not TELEGRAM_USER_ID:
    logger.warning(
        "Warning: TELEGRAM_USER_ID not set in configuration. Bot will be accessible to all."
    )
