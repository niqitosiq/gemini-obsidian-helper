import logging
from services.interfaces import IVaultService  # Зависим от интерфейса

logger = logging.getLogger(__name__)


class CreateFileToolHandler:
    """Обработчик для инструмента создания файла."""

    def __init__(self, vault_service: IVaultService):
        self._vault_service = vault_service

    def execute(self, file_path: str, content: str) -> dict:
        """Выполняет создание файла через VaultService."""
        logger.info(f"Executing CreateFileToolHandler for path: {file_path}")
        success = self._vault_service.create_file(
            relative_path=file_path, content=content
        )
        if success:
            return {
                "status": "success",
                "message": f"File '{file_path}' created successfully.",
            }
        else:
            # VaultService уже залогировал ошибку
            return {
                "status": "error",
                "message": f"Failed to create file '{file_path}'. See logs for details.",
            }
