import logging
from services.interfaces import IVaultService

logger = logging.getLogger(__name__)


class ModifyFileToolHandler:
    """Обработчик для инструмента изменения файла."""

    def __init__(self, vault_service: IVaultService):
        self._vault_service = vault_service

    def execute(self, file_path: str, content: str) -> dict:
        """Выполняет изменение (перезапись) файла через VaultService."""
        logger.info(f"Executing ModifyFileToolHandler for path: {file_path}")
        # Используем modify_file сервиса, который проверяет существование файла
        success = self._vault_service.modify_file(
            relative_path=file_path, content=content
        )
        if success:
            return {
                "status": "success",
                "message": f"File '{file_path}' modified successfully.",
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to modify file '{file_path}'. It might not exist or an error occurred.",
            }
