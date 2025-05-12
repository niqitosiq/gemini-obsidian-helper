import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as path from 'path';

/**
 * Service for handling file paths with base path configuration
 */
@Injectable()
export class FilePathService {
  private basePath: string;
  private readonly logger = new Logger(FilePathService.name);

  constructor(private readonly configService: ConfigService) {
    // Try different environment variable names for the vault path
    this.basePath =
      this.configService.get<string>('OBSIDIAN_VAULT_PATH') ||
      this.configService.get<string>('VAULT_PATH') ||
      this.configService.get<string>('VAULT_DIR') ||
      process.cwd();

    this.logger.log(`Initialized FilePathService with base path: ${this.basePath}`);
  }

  /**
   * Resolve a relative file path to an absolute path using the configured base path
   *
   * @param filePath - The relative file path
   * @returns The absolute file path
   */
  resolveFilePath(filePath: string): string {
    if (path.isAbsolute(filePath)) {
      return filePath;
    }
    return path.join(this.basePath, filePath);
  }

  /**
   * Get the base path
   *
   * @returns The configured base path
   */
  getBasePath(): string {
    return this.basePath;
  }

  /**
   * Get the path to a standard folder in the vault
   *
   * @param folderType - The type of folder ('tasks', 'projects', 'dailyNotes', 'notes')
   * @returns The path to the folder
   */
  getStandardFolderPath(folderType: 'tasks' | 'projects' | 'dailyNotes' | 'notes'): string {
    const folderPaths = {
      tasks: '03 - Tasks',
      projects: '01 - Projects',
      dailyNotes: '02 - Daily Notes',
      notes: '04 - Notes',
    };

    return folderPaths[folderType] || '';
  }

  /**
   * Ensure a directory exists, creating it if necessary
   *
   * @param dirPath - The directory path (relative to base path)
   * @returns The absolute path to the directory
   */
  async ensureDirectoryExists(dirPath: string): Promise<string> {
    const fs = await import('fs/promises');
    const absolutePath = this.resolveFilePath(dirPath);

    try {
      await fs.mkdir(absolutePath, { recursive: true });
    } catch (error) {
      this.logger.error(`Error creating directory ${absolutePath}: ${error.message}`);
      throw error;
    }

    return absolutePath;
  }
}
