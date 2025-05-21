import { Injectable } from '@nestjs/common';
import { ConfigService } from '../../../../shared/infrastructure/config/config.service';
import { IVaultService } from '../../domain/interfaces/vault-service.interface';
import * as fs from 'fs';
import * as path from 'path';
import { promisify } from 'util';
import { EventEmitter } from 'events';

const fsExists = promisify(fs.exists);
const fsReadFile = promisify(fs.readFile);
const fsWriteFile = promisify(fs.writeFile);
const fsReaddir = promisify(fs.readdir);
const fsMkdir = promisify(fs.mkdir);
const fsRm = promisify(fs.rm);
const fsStat = promisify(fs.stat);

@Injectable()
export class VaultService implements IVaultService {
  public readonly fileEvents = new EventEmitter();
  private watcher: fs.FSWatcher | null = null;

  constructor(private readonly configService: ConfigService) {
    this.initFileWatcher();
  }

  private initFileWatcher() {
    const vaultRoot = this.getVaultRoot();
    if (!vaultRoot) {
      console.error('Vault root path is not configured, cannot watch files');
      return;
    }
    try {
      this.watcher = fs.watch(vaultRoot, { recursive: true }, (eventType, filename) => {
        if (filename && filename.endsWith('.md')) {
          // Emit event for changed markdown file
          this.fileEvents.emit('fileChanged', filename);
        }
      });
      console.log('VaultService: Watching for file changes in', vaultRoot);
    } catch (err) {
      console.error('VaultService: Error setting up file watcher:', err);
    }
  }

  getVaultRoot(): string | undefined {
    return this.configService.getObsidianVaultPath();
  }

  resolvePath(relativePath: string): string | undefined {
    const vaultRoot = this.getVaultRoot();
    if (!vaultRoot) {
      console.error('Vault root path is not configured');
      return undefined;
    }

    // Get the current working directory
    const cwd = process.cwd();

    // Clean up both paths - remove any quotes and trailing/leading slashes
    const cleanVaultRoot = vaultRoot.replace(/^["'\.\/\\]+|["'\/\\]+$/g, '');
    const cleanRelativePath = relativePath.replace(/^["'\.\/\\]+|["'\/\\]+$/g, '');

    // Create the absolute path
    const absolutePath = path.resolve(cwd, cleanVaultRoot, cleanRelativePath);

    return absolutePath;
  }

  async createFile(relativePath: string, content: string): Promise<boolean> {
    const absolutePath = this.resolvePath(relativePath);
    if (!absolutePath) {
      return false;
    }

    try {
      // Create parent directories if they don't exist
      const dirPath = path.dirname(absolutePath);
      await this.createDirectoryRecursive(dirPath);

      // Write the file
      await fsWriteFile(absolutePath, content, 'utf8');
      return true;
    } catch (error) {
      console.error(`Error creating file ${relativePath}:`, error);
      return false;
    }
  }

  async modifyFile(relativePath: string, content: string): Promise<boolean> {
    const absolutePath = this.resolvePath(relativePath);
    if (!absolutePath) {
      return false;
    }

    try {
      // Check if file exists
      const exists = await fsExists(absolutePath);
      if (!exists) {
        console.error(`File ${relativePath} does not exist`);
        return false;
      }

      // Write the file
      await fsWriteFile(absolutePath, content, 'utf8');
      return true;
    } catch (error) {
      console.error(`Error modifying file ${relativePath}:`, error);
      return false;
    }
  }

  async deleteFile(relativePath: string): Promise<boolean> {
    const absolutePath = this.resolvePath(relativePath);
    if (!absolutePath) {
      return false;
    }

    try {
      // Check if file exists
      const exists = await fsExists(absolutePath);
      if (!exists) {
        console.error(`File ${relativePath} does not exist`);
        return false;
      }

      // Delete the file
      await fsRm(absolutePath);
      return true;
    } catch (error) {
      console.error(`Error deleting file ${relativePath}:`, error);
      return false;
    }
  }

  async createFolder(relativePath: string): Promise<boolean> {
    const absolutePath = this.resolvePath(relativePath);
    if (!absolutePath) {
      return false;
    }

    try {
      await this.createDirectoryRecursive(absolutePath);
      return true;
    } catch (error) {
      console.error(`Error creating folder ${relativePath}:`, error);
      return false;
    }
  }

  async deleteFolder(relativePath: string): Promise<boolean> {
    const absolutePath = this.resolvePath(relativePath);
    if (!absolutePath) {
      return false;
    }

    try {
      // Check if folder exists
      const exists = await fsExists(absolutePath);
      if (!exists) {
        console.error(`Folder ${relativePath} does not exist`);
        return false;
      }

      // Delete the folder recursively
      await fsRm(absolutePath, { recursive: true });
      return true;
    } catch (error) {
      console.error(`Error deleting folder ${relativePath}:`, error);
      return false;
    }
  }

  async fileExists(relativePath: string): Promise<boolean> {
    const absolutePath = this.resolvePath(relativePath);
    if (!absolutePath) {
      return false;
    }

    try {
      console.log(`Checking if file exists at absolute path: ${absolutePath}`);
      const exists = await fsExists(absolutePath);
      if (!exists) {
        console.log(`File does not exist at path: ${absolutePath}`);
        return false;
      }

      const stats = await fsStat(absolutePath);
      const isFile = stats.isFile();
      console.log(`Path exists and isFile: ${isFile}`);
      return isFile;
    } catch (error) {
      console.error(`Error checking if file ${relativePath} exists:`, error);
      return false;
    }
  }

  async readFile(relativePath: string): Promise<string | undefined> {
    const absolutePath = this.resolvePath(relativePath);
    if (!absolutePath) {
      return undefined;
    }

    try {
      // Check if file exists
      console.log(`Attempting to read file at: ${absolutePath}`);
      const exists = await fsExists(absolutePath);
      if (!exists) {
        console.error(`File does not exist at path: ${absolutePath}`);
        return undefined;
      }

      // Read the file
      const content = await fsReadFile(absolutePath, 'utf8');
      console.log(`Successfully read file with size: ${content.length} bytes`);
      return content;
    } catch (error) {
      console.error(`Error reading file ${relativePath}:`, error);
      return undefined;
    }
  }

  async folderExists(relativePath: string): Promise<boolean> {
    const absolutePath = this.resolvePath(relativePath);
    if (!absolutePath) {
      return false;
    }

    try {
      const exists = await fsExists(absolutePath);
      if (!exists) {
        return false;
      }

      const stats = await fsStat(absolutePath);
      return stats.isDirectory();
    } catch (error) {
      console.error(`Error checking if folder ${relativePath} exists:`, error);
      return false;
    }
  }

  async listFiles(relativePath: string = '.'): Promise<string[] | undefined> {
    const absolutePath = this.resolvePath(relativePath);
    if (!absolutePath) {
      return undefined;
    }

    try {
      // Check if folder exists
      const exists = await fsExists(absolutePath);
      if (!exists) {
        console.error(`Folder ${relativePath} does not exist`);
        return undefined;
      }

      // Read the directory
      const files = await fsReaddir(absolutePath);
      return files;
    } catch (error) {
      console.error(`Error listing files in ${relativePath}:`, error);
      return undefined;
    }
  }

  async readAllMarkdownFiles(): Promise<Record<string, string>> {
    const vaultRoot = this.getVaultRoot();
    if (!vaultRoot) {
      console.error('Vault root path is not configured');
      return {};
    }

    const result: Record<string, string> = {};
    await this.readMarkdownFilesRecursive(vaultRoot, '', result);
    return result;
  }

  // Helper methods
  private async createDirectoryRecursive(dirPath: string): Promise<void> {
    try {
      await fsMkdir(dirPath, { recursive: true });
    } catch (error) {
      console.error(`Error creating directory ${dirPath}:`, error);
      throw error;
    }
  }

  private async readMarkdownFilesRecursive(
    baseDir: string,
    relativePath: string,
    result: Record<string, string>,
  ): Promise<void> {
    const currentDir = path.join(baseDir, relativePath);

    try {
      const entries = await fsReaddir(currentDir, { withFileTypes: true });

      for (const entry of entries) {
        const entryRelativePath = path.join(relativePath, entry.name);
        const entryAbsolutePath = path.join(baseDir, entryRelativePath);

        if (entry.isDirectory()) {
          // Recursively process subdirectories
          await this.readMarkdownFilesRecursive(baseDir, entryRelativePath, result);
        } else if (entry.isFile() && entry.name.endsWith('.md')) {
          // Read markdown files
          try {
            const content = await fsReadFile(entryAbsolutePath, 'utf8');
            result[entryRelativePath] = content;
          } catch (error) {
            console.error(`Error reading markdown file ${entryRelativePath}:`, error);
          }
        }
      }
    } catch (error) {
      console.error(`Error reading directory ${relativePath}:`, error);
    }
  }
}
