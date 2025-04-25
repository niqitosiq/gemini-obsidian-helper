import logging
from services.interfaces import IVaultService

logger = logging.getLogger(__name__)


class DeleteFolderToolHandler:
    """Обработчик для инструмента удаления папки."""

    def __init__(self, vault_service: IVaultService):
        self._vault_service = vault_service

    def execute(self, folder_path: str) -> dict:
        """Выполняет удаление папки через VaultService."""
        logger.info(f"Executing DeleteFolderToolHandler for path: {folder_path}")
        success = self._vault_service.delete_folder(relative_path=folder_path)
        if success:
            return {
                "status": "success",
                "message": f"Folder '{folder_path}' deleted successfully.",
            }
        else:
            # Сервис логгирует критическую ошибку при попытке удаления корня
            return {
                "status": "error",
                "message": f"Failed to delete folder '{folder_path}'. It might not exist or be the vault root.",
            }
