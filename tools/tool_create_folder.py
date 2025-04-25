import logging
from services.interfaces import IVaultService

logger = logging.getLogger(__name__)


class CreateFolderToolHandler:
    """Обработчик для инструмента создания папки."""

    def __init__(self, vault_service: IVaultService):
        self._vault_service = vault_service

    def execute(self, folder_path: str) -> dict:
        """Выполняет создание папки через VaultService."""
        logger.info(f"Executing CreateFolderToolHandler for path: {folder_path}")
        success = self._vault_service.create_folder(relative_path=folder_path)
        if success:
            return {
                "status": "success",
                "message": f"Folder '{folder_path}' created or already exists.",
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to create folder '{folder_path}'.",
            }
