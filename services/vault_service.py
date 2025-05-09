import os
import shutil
import logging
import pathlib  # Import pathlib
from typing import Optional, List, Dict, Any  # Add Dict, Any

from .interfaces import IVaultService, IConfigService

logger = logging.getLogger(__name__)


class VaultServiceImpl(IVaultService):
    """
    Реализация сервиса для безопасного взаимодействия с файловой системой Obsidian Vault.
    """

    _vault_root: Optional[str] = None

    def __init__(self, config_service: IConfigService):
        self._config_service = config_service
        self._initialize_vault_root()
        logger.debug(f"VaultService initialized. Root: {self._vault_root}")

    def _initialize_vault_root(self):
        """Получает и валидирует путь к хранилищу из конфигурации."""
        vault_path = self._config_service.get_obsidian_vault_path()
        if not vault_path:
            logger.error(
                "OBSIDIAN_VAULT_PATH is not configured. VaultService cannot operate."
            )
            self._vault_root = None
            return
        if not os.path.isdir(vault_path):
            logger.error(
                f"Configured OBSIDIAN_VAULT_PATH '{vault_path}' is not a valid directory."
            )
            self._vault_root = None
            return

        self._vault_root = os.path.abspath(vault_path)

    def get_vault_root(self) -> Optional[str]:
        """Возвращает абсолютный путь к корню Obsidian Vault."""
        return self._vault_root

    def resolve_path(self, relative_path: str) -> Optional[str]:
        """
        Преобразует относительный путь внутри хранилища в безопасный абсолютный путь.
        Возвращает None, если путь небезопасен, выходит за пределы хранилища или сервис не инициализирован.
        """
        if self._vault_root is None:
            logger.error("Vault root is not initialized, cannot resolve path.")
            return None

        # Очистка относительного пути
        clean_relative_path = relative_path.strip().lstrip("/\\")

        # Предотвращение использования абсолютных путей в relative_path
        if os.path.isabs(clean_relative_path):
            logger.error(
                f"Absolute paths are not allowed in relative_path: '{relative_path}'"
            )
            return None

        unsafe_path = os.path.join(self._vault_root, clean_relative_path)

        # Нормализация пути (разрешает .., ., // и т.д.)
        resolved_path = os.path.normpath(unsafe_path)

        # Проверка безопасности: убеждаемся, что разрешенный путь находится внутри корня хранилища
        # Используем realpath для разрешения символических ссылок перед проверкой
        real_base_path = os.path.realpath(self._vault_root)
        real_resolved_path = os.path.realpath(resolved_path)

        if os.path.commonpath([real_base_path]) == os.path.commonpath(
            [real_base_path, real_resolved_path]
        ):
            # Дополнительная проверка, чтобы убедиться, что мы не просто получили сам vault_root из-за ошибки пути
            if real_resolved_path.startswith(real_base_path):
                return resolved_path  # Возвращаем не realpath, а нормализованный путь для сохранения регистра и т.д.
        # Если не прошли проверку
        logger.error(
            f"Path traversal attempt detected or path resolved outside vault: "
            f"Relative='{relative_path}', Resolved='{resolved_path}', RealResolved='{real_resolved_path}', VaultRoot='{self._vault_root}'"
        )
        return None

    def create_file(self, relative_path: str, content: str) -> bool:
        """Создает или перезаписывает файл по относительному пути с указанным содержимым."""
        safe_path = self.resolve_path(relative_path)
        if not safe_path:
            logger.error(f"Cannot create file due to unsafe path: {relative_path}")
            return False
        try:
            dir_name = os.path.dirname(safe_path)
            # Создаем директории, если их нет
            os.makedirs(dir_name, exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(
                f"File created/overwritten successfully: {safe_path} (relative: {relative_path})"
            )
            return True
        except OSError as e:
            logger.error(
                f"OS error creating/writing file '{safe_path}': {e}", exc_info=True
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error creating/writing file '{safe_path}': {e}",
                exc_info=True,
            )
            return False

    def modify_file(self, relative_path: str, content: str) -> bool:
        """Перезаписывает существующий файл по относительному пути."""
        safe_path = self.resolve_path(relative_path)
        if not safe_path:
            logger.error(f"Cannot modify file due to unsafe path: {relative_path}")
            return False

        # Проверяем, что файл существует перед перезаписью
        if not os.path.exists(safe_path):
            logger.error(
                f"File not found for modification: {safe_path} (relative: {relative_path})"
            )
            return False
        if not os.path.isfile(safe_path):
            logger.error(f"Path is not a file, cannot modify: {safe_path}")
            return False

        return self.create_file(
            relative_path, content
        )  # Используем логику create_file для перезаписи

    def delete_file(self, relative_path: str) -> bool:
        """Удаляет файл по относительному пути."""
        safe_path = self.resolve_path(relative_path)
        if not safe_path:
            logger.error(f"Cannot delete file due to unsafe path: {relative_path}")
            return False
        try:
            if not os.path.exists(safe_path):
                logger.warning(
                    f"File not found for deletion: {safe_path} (relative: {relative_path})"
                )
                return False  # Или True, если "нет файла -> удален"? Пока False.
            if not os.path.isfile(safe_path):
                logger.error(f"Path is not a file, cannot delete: {safe_path}")
                return False

            os.remove(safe_path)
            logger.info(
                f"File deleted successfully: {safe_path} (relative: {relative_path})"
            )
            return True
        except OSError as e:
            logger.error(f"OS error deleting file '{safe_path}': {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error deleting file '{safe_path}': {e}", exc_info=True
            )
            return False

    def create_folder(self, relative_path: str) -> bool:
        """Создает папку по относительному пути (включая родительские)."""
        safe_path = self.resolve_path(relative_path)
        if not safe_path:
            logger.error(f"Cannot create folder due to unsafe path: {relative_path}")
            return False
        try:
            os.makedirs(safe_path, exist_ok=True)
            logger.info(
                f"Folder created or already exists: {safe_path} (relative: {relative_path})"
            )
            return True
        except OSError as e:
            logger.error(f"OS error creating folder '{safe_path}': {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error creating folder '{safe_path}': {e}", exc_info=True
            )
            return False

    def delete_folder(self, relative_path: str) -> bool:
        """Удаляет папку по относительному пути (рекурсивно)."""
        safe_path = self.resolve_path(relative_path)
        if not safe_path:
            logger.error(f"Cannot delete folder due to unsafe path: {relative_path}")
            return False

        # Критическая проверка: не удалять корень хранилища!
        if safe_path == self._vault_root:
            logger.critical(
                f"CRITICAL SAFETY FUSE: Attempted to delete the vault root directory! Path: {safe_path}"
            )
            return False

        try:
            if not os.path.exists(safe_path):
                logger.warning(
                    f"Folder not found for deletion: {safe_path} (relative: {relative_path})"
                )
                return False
            if not os.path.isdir(safe_path):
                logger.error(f"Path is not a directory, cannot delete: {safe_path}")
                return False

            shutil.rmtree(safe_path)
            logger.info(
                f"Folder deleted successfully: {safe_path} (relative: {relative_path})"
            )
            return True
        except OSError as e:
            logger.error(f"OS error deleting folder '{safe_path}': {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error deleting folder '{safe_path}': {e}", exc_info=True
            )
            return False

    def read_file(self, relative_path: str) -> Optional[str]:
        """Читает содержимое файла по относительному пути."""
        safe_path = self.resolve_path(relative_path)
        if not safe_path:
            logger.error(f"Cannot read file due to unsafe path: {relative_path}")
            return None
        try:
            if not self.file_exists(
                relative_path
            ):  # Используем file_exists для проверки
                logger.warning(
                    f"File not found for reading: {safe_path} (relative: {relative_path})"
                )
                return None

            with open(safe_path, "r", encoding="utf-8") as f:
                content = f.read()
            # logger.debug(f"File read successfully: {safe_path}") # Может быть слишком много логов
            return content
        except OSError as e:
            logger.error(f"OS error reading file '{safe_path}': {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error reading file '{safe_path}': {e}", exc_info=True
            )
            return None

    def file_exists(self, relative_path: str) -> bool:
        """Проверяет существование файла по относительному пути."""
        safe_path = self.resolve_path(relative_path)
        if not safe_path:
            return False
        return os.path.isfile(safe_path)

    def folder_exists(self, relative_path: str) -> bool:
        """Проверяет существование папки по относительному пути."""
        safe_path = self.resolve_path(relative_path)
        if not safe_path:
            return False
        return os.path.isdir(safe_path)

    def list_files(self, relative_path: str = ".") -> Optional[List[str]]:
        """Возвращает список файлов и папок в указанной относительной директории."""
        safe_path = self.resolve_path(relative_path)
        if not safe_path:
            logger.error(f"Cannot list files due to unsafe path: {relative_path}")
            return None
        if not os.path.isdir(safe_path):
            logger.error(f"Cannot list files, path is not a directory: {safe_path}")
            return None
        try:
            entries = os.listdir(safe_path)
            logger.debug(f"Listed directory: {safe_path}")
            return entries
        except OSError as e:
            logger.error(
                f"OS error listing directory '{safe_path}': {e}", exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error listing directory '{safe_path}': {e}", exc_info=True
            )
            return None

    def read_all_markdown_files(self) -> Dict[str, str]:
        """
        Рекурсивно читает все markdown файлы (.md) в хранилище.
        Возвращает словарь, где ключ - относительный путь файла от корня хранилища,
        а значение - содержимое файла.
        """
        if self._vault_root is None:
            logger.error(
                "Vault root is not initialized, cannot read all markdown files."
            )
            return {}

        markdown_files: Dict[str, str] = {}
        vault_path = pathlib.Path(self._vault_root)

        try:
            for file_path in vault_path.rglob("*.md"):
                if file_path.is_file():
                    try:
                        relative_path_obj = file_path.relative_to(vault_path)
                        # Use as_posix() for consistent path separators
                        relative_path_str = relative_path_obj.as_posix()
                        content = file_path.read_text(encoding="utf-8")
                        markdown_files[relative_path_str] = content
                        # logger.debug(f"Read markdown file: {relative_path_str}") # Too verbose
                    except UnicodeDecodeError as e:
                        logger.warning(
                            f"Could not decode file {file_path} as UTF-8: {e}"
                        )
                    except OSError as e:
                        logger.warning(f"OS error reading file {file_path}: {e}")
                    except Exception as e:
                        logger.warning(
                            f"Unexpected error reading file {file_path}: {e}"
                        )
        except Exception as e:
            logger.error(
                f"Error during recursive search for markdown files in {vault_path}: {e}",
                exc_info=True,
            )
            return {}  # Return empty dict on major error during search

        logger.info(f"Read {len(markdown_files)} markdown files from vault.")
        return markdown_files
