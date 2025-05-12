import { Injectable, Inject } from '@nestjs/common';
import { IToolHandler } from '../../domain/interfaces/tool-handler.interface';
import { IVaultService } from '../../../vault/domain/interfaces/vault-service.interface';

@Injectable()
export class CreateFileToolHandler implements IToolHandler {
  constructor(@Inject('IVaultService') private readonly vaultService: IVaultService) {}

  async execute(params: Record<string, any>): Promise<Record<string, any>> {
    const { path, content } = params;

    if (!path || typeof path !== 'string') {
      return {
        status: 'error',
        message: 'Path parameter is required and must be a string',
      };
    }

    if (content === undefined || content === null) {
      return {
        status: 'error',
        message: 'Content parameter is required',
      };
    }

    const contentStr = typeof content === 'string' ? content : JSON.stringify(content, null, 2);

    try {
      const success = await this.vaultService.createFile(path, contentStr);

      if (success) {
        return {
          status: 'success',
          message: `File created successfully at ${path}`,
          path,
        };
      } else {
        return {
          status: 'error',
          message: `Failed to create file at ${path}`,
        };
      }
    } catch (error) {
      return {
        status: 'error',
        message: `Error creating file: ${error.message || error}`,
      };
    }
  }
}

@Injectable()
export class ModifyFileToolHandler implements IToolHandler {
  constructor(@Inject('IVaultService') private readonly vaultService: IVaultService) {}

  async execute(params: Record<string, any>): Promise<Record<string, any>> {
    const { path, content } = params;

    if (!path || typeof path !== 'string') {
      return {
        status: 'error',
        message: 'Path parameter is required and must be a string',
      };
    }

    if (content === undefined || content === null) {
      return {
        status: 'error',
        message: 'Content parameter is required',
      };
    }

    const contentStr = typeof content === 'string' ? content : JSON.stringify(content, null, 2);

    try {
      // Check if file exists
      const exists = await this.vaultService.fileExists(path);

      if (!exists) {
        return {
          status: 'error',
          message: `File does not exist at ${path}`,
        };
      }

      const success = await this.vaultService.modifyFile(path, contentStr);

      if (success) {
        return {
          status: 'success',
          message: `File modified successfully at ${path}`,
          path,
        };
      } else {
        return {
          status: 'error',
          message: `Failed to modify file at ${path}`,
        };
      }
    } catch (error) {
      return {
        status: 'error',
        message: `Error modifying file: ${error.message || error}`,
      };
    }
  }
}

@Injectable()
export class DeleteFileToolHandler implements IToolHandler {
  constructor(@Inject('IVaultService') private readonly vaultService: IVaultService) {}

  async execute(params: Record<string, any>): Promise<Record<string, any>> {
    const { path } = params;

    if (!path || typeof path !== 'string') {
      return {
        status: 'error',
        message: 'Path parameter is required and must be a string',
      };
    }

    try {
      // Check if file exists
      const exists = await this.vaultService.fileExists(path);

      if (!exists) {
        return {
          status: 'error',
          message: `File does not exist at ${path}`,
        };
      }

      const success = await this.vaultService.deleteFile(path);

      if (success) {
        return {
          status: 'success',
          message: `File deleted successfully at ${path}`,
          path,
        };
      } else {
        return {
          status: 'error',
          message: `Failed to delete file at ${path}`,
        };
      }
    } catch (error) {
      return {
        status: 'error',
        message: `Error deleting file: ${error.message || error}`,
      };
    }
  }
}
