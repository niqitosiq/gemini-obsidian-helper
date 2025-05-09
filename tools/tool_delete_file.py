import logging
from services.interfaces import IVaultService

logger = logging.getLogger(__name__)


class DeleteFileToolHandler:
    """Обработчик для инструмента удаления файла."""

    def __init__(self, vault_service: IVaultService):
        self._vault_service = vault_service

    def execute(self, file_path: str) -> dict:
        """Выполняет удаление файла через VaultService."""
        logger.info(f"Executing DeleteFileToolHandler for path: {file_path}")
        success = self._vault_service.delete_file(relative_path=file_path)
        if success:
            return {
                "status": "success",
                "message": f"File '{file_path}' deleted successfully.",
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to delete file '{file_path}'. It might not exist or an error occurred.",
            }
