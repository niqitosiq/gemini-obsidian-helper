import os
import logging
from dotenv import load_dotenv
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# Загрузка .env файла остается для локальной разработки
load_dotenv()

_loaded_config: Optional[Dict[str, Optional[str]]] = None


def load_app_config() -> Dict[str, Optional[str]]:
    """
    Загружает конфигурацию из переменных окружения и возвращает ее в виде словаря.
    Выполняет базовую валидацию наличия ключевых переменных.
    """
    global _loaded_config
    if _loaded_config is not None:
        return _loaded_config

    config_data = {
        # --- API Keys ---
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        # --- Model Settings ---
        "GEMINI_MODEL_NAME": os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash"),
        # --- Telegram Settings ---
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_USER_ID_LIST": os.getenv("TELEGRAM_USER_ID"),  # Загружаем как строку
        # --- Obsidian Settings ---
        "OBSIDIAN_DAILY_NOTES_FOLDER": os.getenv("OBSIDIAN_DAILY_NOTES_FOLDER"),
        "OBSIDIAN_VAULT_PATH": os.getenv("OBSIDIAN_VAULT_PATH"),
        # --- Application Settings ---
        # "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"), # Пример
    }

    # --- Валидации (остаются как предупреждения при загрузке) ---
    if not config_data["GEMINI_API_KEY"]:
        logger.warning(
            "GEMINI_API_KEY environment variable not set. LLM functionality will be disabled."
        )
    if not config_data["TELEGRAM_BOT_TOKEN"]:
        logger.warning(
            "TELEGRAM_BOT_TOKEN environment variable not set. Telegram bot functionality may be disabled."
        )
    if not config_data["TELEGRAM_USER_ID_LIST"]:
        logger.warning(
            "TELEGRAM_USER_ID environment variable not set. Telegram bot may not restrict users."
        )
    else:
        # Преобразуем строку ID пользователей в список строк
        user_ids = [
            uid.strip()
            for uid in config_data["TELEGRAM_USER_ID_LIST"].split(",")
            if uid.strip()
        ]
        config_data["TELEGRAM_USER_ID_LIST"] = user_ids  # Сохраняем как список

    if not config_data["OBSIDIAN_DAILY_NOTES_FOLDER"]:
        logger.warning(
            "OBSIDIAN_DAILY_NOTES_FOLDER environment variable not set. Obsidian integration may be disabled."
        )
    if not config_data["OBSIDIAN_VAULT_PATH"]:
        logger.warning(
            "OBSIDIAN_VAULT_PATH environment variable not set. Obsidian integration may be disabled or use a default path."
        )

    _loaded_config = config_data
    logger.info("Application configuration loaded.")
    return _loaded_config


# Больше не экспортируем константы напрямую
# GEMINI_API_KEY = _get_config_value("GEMINI_API_KEY")
# ... и т.д.
