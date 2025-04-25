import logging
from typing import Dict, Optional, List, Any
from .interfaces import IConfigService

logger = logging.getLogger(__name__)


class ConfigServiceImpl(IConfigService):
    """Реализация сервиса конфигурации, читающая из словаря."""

    def __init__(self, config_data: Dict[str, Optional[Any]]):
        self._config = config_data
        logger.debug("ConfigService initialized.")

    def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        return self._config.get(key, default)

    def get_str(self, key: str, default: Optional[str] = None) -> Optional[str]:
        value = self.get(key, default)
        return str(value) if value is not None else None

    def get_list_str(
        self, key: str, default: Optional[List[str]] = None
    ) -> Optional[List[str]]:
        value = self.get(key)  # Получаем значение (может быть уже списком)
        if isinstance(value, list):
            return value
        elif value is None:
            return default
        else:
            # Попытка вернуть как список из одного элемента, если это строка? Или вернуть default?
            # Для TELEGRAM_USER_ID_LIST мы уже преобразовали в список в config/__init__.py
            logger.warning(
                f"Expected list for config key '{key}', but got {type(value)}. Returning default."
            )
            return default

    def get_gemini_api_key(self) -> Optional[str]:
        return self.get_str("GEMINI_API_KEY")

    def get_gemini_model_name(self) -> str:
        # Гарантированно вернет строку, т.к. есть значение по умолчанию в load_app_config
        return self.get_str("GEMINI_MODEL_NAME", "gemini-2.0-flash")  # type: ignore

    def get_telegram_bot_token(self) -> Optional[str]:
        return self.get_str("TELEGRAM_BOT_TOKEN")

    def get_telegram_user_ids(self) -> List[str]:
        # load_app_config уже возвращает список или None
        user_ids = self.get_list_str("TELEGRAM_USER_ID_LIST", default=[])
        return user_ids if user_ids is not None else []

    def get_obsidian_vault_path(self) -> Optional[str]:
        return self.get_str("OBSIDIAN_VAULT_PATH")

    def get_obsidian_daily_notes_folder(self) -> Optional[str]:
        return self.get_str("OBSIDIAN_DAILY_NOTES_FOLDER")
