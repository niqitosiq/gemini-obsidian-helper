import { Injectable, Inject, Logger, OnModuleDestroy, forwardRef } from '@nestjs/common';
import { IToolHandler } from '../../domain/interfaces/tool-handler.interface';
import * as fs from 'fs/promises';
import * as path from 'path';
import { FilePathService } from './file-path.service';
import { SendMessageService } from '../../../telegram/application/services/send-message.service';

/**
 * Tool implementation for creating files
 */
@Injectable()
export class CreateFileToolHandler implements IToolHandler {
  constructor(private readonly filePathService: FilePathService) {}

  /**
   * Create a file with the given path and content
   *
   * @param params - Object containing file_path and content
   * @returns Result of the operation
   */
  async execute(params: Record<string, any>): Promise<Record<string, any>> {
    try {
      const { file_path, content } = params;

      if (!file_path || !content) {
        return {
          status: 'error',
          message: 'Missing required parameters: file_path and content',
        };
      }

      // Resolve the absolute file path using the base path
      const absoluteFilePath = this.filePathService.resolveFilePath(file_path);

      // Ensure directory exists
      const dirPath = path.dirname(absoluteFilePath);
      await fs.mkdir(dirPath, { recursive: true });

      // Write file content
      await fs.writeFile(absoluteFilePath, content, 'utf8');

      return {
        status: 'success',
        message: `File created successfully: ${file_path}`,
        file_path,
        absolute_path: absoluteFilePath,
      };
    } catch (error) {
      return {
        status: 'error',
        message: `Error creating file: ${error.message || error}`,
      };
    }
  }
}

/**
 * Tool implementation for modifying existing files
 */
@Injectable()
export class ModifyFileToolHandler implements IToolHandler {
  constructor(private readonly filePathService: FilePathService) {}

  /**
   * Modify an existing file with new content
   *
   * @param params - Object containing file_path and content
   * @returns Result of the operation
   */
  async execute(params: Record<string, any>): Promise<Record<string, any>> {
    try {
      const { file_path, content } = params;

      if (!file_path || content === undefined) {
        return {
          status: 'error',
          message: 'Missing required parameters: file_path and content',
        };
      }

      // Resolve the absolute file path using the base path
      const absoluteFilePath = this.filePathService.resolveFilePath(file_path);

      // Check if file exists
      try {
        await fs.access(absoluteFilePath);
      } catch (error) {
        return {
          status: 'error',
          message: `File not found: ${file_path} (${absoluteFilePath})`,
        };
      }

      // Write new content to file
      await fs.writeFile(absoluteFilePath, content, 'utf8');

      return {
        status: 'success',
        message: `File modified successfully: ${file_path}`,
        file_path,
        absolute_path: absoluteFilePath,
      };
    } catch (error) {
      return {
        status: 'error',
        message: `Error modifying file: ${error.message || error}`,
      };
    }
  }
}

/**
 * Tool implementation for deleting files
 */
@Injectable()
export class DeleteFileToolHandler implements IToolHandler {
  constructor(private readonly filePathService: FilePathService) {}

  /**
   * Delete a file at the given path
   *
   * @param params - Object containing file_path
   * @returns Result of the operation
   */
  async execute(params: Record<string, any>): Promise<Record<string, any>> {
    try {
      const { file_path } = params;

      if (!file_path) {
        return {
          status: 'error',
          message: 'Missing required parameter: file_path',
        };
      }

      // Resolve the absolute file path using the base path
      const absoluteFilePath = this.filePathService.resolveFilePath(file_path);

      // Check if file exists
      try {
        await fs.access(absoluteFilePath);
      } catch (error) {
        return {
          status: 'error',
          message: `File not found: ${file_path} (${absoluteFilePath})`,
        };
      }

      // Delete the file
      await fs.unlink(absoluteFilePath);

      return {
        status: 'success',
        message: `File deleted successfully: ${file_path}`,
        file_path,
        absolute_path: absoluteFilePath,
      };
    } catch (error) {
      return {
        status: 'error',
        message: `Error deleting file: ${error.message || error}`,
      };
    }
  }
}

/**
 * Tool implementation for sending replies to the user
 */
@Injectable()
export class ReplyToolHandler implements IToolHandler {
  private readonly logger = new Logger(ReplyToolHandler.name);

  constructor(
    @Inject(forwardRef(() => SendMessageService))
    private readonly sendMessageService: SendMessageService,
  ) {}

  /**
   * Send a reply message to the user
   *
   * @param params - Object containing message content and either chat_id or user_id
   * @returns Result of the operation
   */
  async execute(params: Record<string, any>): Promise<Record<string, any>> {
    try {
      const { message, chat_id, user_id } = params;

      if (!message) {
        return {
          status: 'error',
          message: 'Missing required parameter: message',
        };
      }

      // Check if we have either chat_id or user_id
      if (!chat_id && !user_id) {
        this.logger.warn('No chat_id or user_id provided for reply, cannot send message');
        return {
          status: 'error',
          message: 'Missing required parameter: either chat_id or user_id',
        };
      }

      // If chat_id is provided, prioritize it
      if (chat_id) {
        const numericChatId = parseInt(chat_id, 10);
        if (isNaN(numericChatId)) {
          this.logger.error(`Invalid chat_id: ${chat_id}`);
          return {
            status: 'error',
            message: `Invalid chat_id: ${chat_id}`,
          };
        }

        this.logger.log(`Sending message to chat ${numericChatId}`);
        const result = await this.sendMessageService.sendMessage(
          numericChatId,
          message,
          'Markdown',
        );

        if (result) {
          return {
            status: 'success',
            message: 'Reply sent successfully',
          };
        } else {
          return {
            status: 'error',
            message: 'Failed to send reply',
          };
        }
      }

      // If we reached here, we must have a user_id but no chat_id
      const numericUserId = parseInt(user_id, 10);
      if (isNaN(numericUserId)) {
        this.logger.error(`Invalid user_id: ${user_id}`);
        return {
          status: 'error',
          message: `Invalid user_id: ${user_id}`,
        };
      }

      this.logger.log(`Sending message to user ${numericUserId}`);
      const result = await this.sendMessageService.sendMessage(numericUserId, message, 'Markdown');

      if (result) {
        return {
          status: 'success',
          message: 'Reply sent successfully',
        };
      } else {
        return {
          status: 'error',
          message: 'Failed to send reply to user',
        };
      }
    } catch (error) {
      this.logger.error(`Error sending reply: ${error.message || error}`, error.stack);
      return {
        status: 'error',
        message: `Error sending reply: ${error.message || error}`,
      };
    }
  }
}

/**
 * Tool implementation for ending the conversation
 */
@Injectable()
export class FinishToolHandler implements IToolHandler {
  /**
   * Mark the conversation as finished
   *
   * @param params - No parameters required
   * @returns Result of the operation
   */
  async execute(params: Record<string, any>): Promise<Record<string, any>> {
    return {
      status: 'success',
      message: 'Conversation finished',
      finished: true,
    };
  }
}
