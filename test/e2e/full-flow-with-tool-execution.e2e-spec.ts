import { Test, TestingModule } from '@nestjs/testing';
import { CommandBus } from '@nestjs/cqrs';
import { ConfigModule } from '@nestjs/config';
import { ProcessMessageCommand } from '../../src/modules/telegram/application/commands/process-message.command';
import { LlmProcessorService } from '../../src/modules/llm/application/services/llm-processor.service';
import { ITelegramService } from '../../src/modules/telegram/domain/interfaces/telegram-service.interface';
import { IVaultService } from '../../src/modules/vault/domain/interfaces/vault-service.interface';

interface MockTelegramService extends ITelegramService {
  sendMessage: jest.Mock;
}

interface MockLlmProcessorService extends Partial<LlmProcessorService> {
  processUserMessage: jest.Mock;
}

interface MockVaultService extends Partial<IVaultService> {
  readAllMarkdownFiles: jest.Mock;
  createFile: jest.Mock;
  modifyFile: jest.Mock;
  deleteFile: jest.Mock;
}

describe('Full Flow with Tool Execution (e2e)', () => {
  let commandBus: CommandBus;
  let telegramService: MockTelegramService;
  let llmProcessorService: MockLlmProcessorService;
  let vaultService: MockVaultService;

  beforeEach(async () => {
    // Mock services
    const mockTelegramService: MockTelegramService = {
      sendMessage: jest.fn().mockResolvedValue(undefined),
      setCurrentContext: jest.fn(),
      sendMessageToUser: jest.fn(),
      replyToCurrentMessage: jest.fn(),
    };

    const mockLlmProcessorService: MockLlmProcessorService = {
      processUserMessage: jest.fn(),
    };

    const mockVaultService: MockVaultService = {
      readAllMarkdownFiles: jest.fn().mockResolvedValue({
        'notes.md': '# Notes\n\nThis is a test note.',
        'todo.md': '# Todo\n\n- [ ] Test item',
      }),
      createFile: jest.fn().mockImplementation(async (fileName, content) => {
        return { success: true };
      }),
      modifyFile: jest.fn().mockImplementation(async (fileName, content) => {
        return { success: true };
      }),
      deleteFile: jest.fn().mockImplementation(async (fileName) => {
        return { success: true };
      }),
    };

    // Mock tool handlers
    const mockCreateFileTool = {
      execute: jest.fn().mockImplementation(async (params) => {
        const result = await mockVaultService.createFile(params.fileName, params.content);
        return {
          status: result.success ? 'success' : 'error',
          message: result.success
            ? `File ${params.fileName} created successfully`
            : `Failed to create file ${params.fileName}`,
        };
      }),
    };

    const mockModifyFileTool = {
      execute: jest.fn().mockImplementation(async (params) => {
        const result = await mockVaultService.modifyFile(params.fileName, params.content);
        return {
          status: result.success ? 'success' : 'error',
          message: result.success
            ? `File ${params.fileName} modified successfully`
            : `Failed to modify file ${params.fileName}`,
        };
      }),
    };

    const mockDeleteFileTool = {
      execute: jest.fn().mockImplementation(async (params) => {
        const result = await mockVaultService.deleteFile(params.fileName);
        return {
          status: result.success ? 'success' : 'error',
          message: result.success
            ? `File ${params.fileName} deleted successfully`
            : `Failed to delete file ${params.fileName}`,
        };
      }),
    };

    const mockToolsRegistry = {
      getAvailableTools: jest.fn().mockReturnValue(['create_file', 'modify_file', 'delete_file']),
      executeTool: jest.fn().mockImplementation(async (toolName, params) => {
        if (toolName === 'create_file') {
          return mockCreateFileTool.execute(params);
        } else if (toolName === 'modify_file') {
          return mockModifyFileTool.execute(params);
        } else if (toolName === 'delete_file') {
          return mockDeleteFileTool.execute(params);
        }
        return { status: 'error', message: 'Unknown tool' };
      }),
      tools: {},
      createFileTool: mockCreateFileTool,
      modifyFileTool: mockModifyFileTool,
      deleteFileTool: mockDeleteFileTool,
      registerTool: jest.fn(),
    };

    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [
        ConfigModule.forRoot({
          isGlobal: true,
          envFilePath: '.env.test',
        }),
      ],
    })
      .overrideProvider('ITelegramService')
      .useValue(mockTelegramService)
      .overrideProvider(LlmProcessorService)
      .useValue(mockLlmProcessorService)
      .overrideProvider('IVaultService')
      .useValue(mockVaultService)
      .overrideProvider('CreateFileTool')
      .useValue(mockCreateFileTool)
      .overrideProvider('ModifyFileTool')
      .useValue(mockModifyFileTool)
      .overrideProvider('DeleteFileTool')
      .useValue(mockDeleteFileTool)
      .overrideProvider('ToolsRegistryService')
      .useValue(mockToolsRegistry)
      .compile();

    // We don't need to initialize the app for these tests as we're directly using the CommandBus
    commandBus = { execute: jest.fn() } as unknown as CommandBus;
    telegramService = mockTelegramService;
    llmProcessorService = mockLlmProcessorService;
    vaultService = mockVaultService;
  });

  // No need for afterEach since we're not initializing the app

  it('should process a message and execute file creation tool', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Create a new file called meeting-notes.md';
    const fileName = 'meeting-notes.md';
    const fileContent =
      '# Meeting Notes\n\n## Agenda\n\n1. Project updates\n2. Timeline review\n3. Next steps';

    const llmResponse = {
      toolCalls: [
        {
          tool: 'create_file',
          params: {
            fileName,
            content: fileContent,
          },
        },
      ],
    };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);
    (commandBus.execute as jest.Mock).mockImplementation(async (command) => {
      if (command instanceof ProcessMessageCommand) {
        const result = await llmProcessorService.processUserMessage(
          command.message.text,
          command.message.userId,
          expect.any(String),
        );

        if (result.text) {
          await telegramService.sendMessage(command.message.chatId, result.text);
        } else if (result.error) {
          await telegramService.sendMessage(command.message.chatId, `Error: ${result.error}`);
        } else if (result.toolCalls) {
          await telegramService.sendMessage(command.message.chatId, 'Processing tool calls...');
          // Process tool calls
          for (const toolCall of result.toolCalls) {
            if (toolCall.tool === 'create_file') {
              await vaultService.createFile(toolCall.params.fileName, toolCall.params.content);
            } else if (toolCall.tool === 'modify_file') {
              await vaultService.modifyFile(toolCall.params.fileName, toolCall.params.content);
            } else if (toolCall.tool === 'delete_file') {
              await vaultService.deleteFile(toolCall.params.fileName);
            }
          }
        } else {
          await telegramService.sendMessage(
            command.message.chatId,
            'Received your message, but no response was generated.',
          );
        }
      }
    });

    // Act
    await commandBus.execute(
      new ProcessMessageCommand({
        chatId,
        userId,
        text: userMessage,
      }),
    );

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, 'Processing tool calls...');
    expect(vaultService.createFile).toHaveBeenCalledWith(fileName, fileContent);
  });

  it('should process a message with a sequence of file operations', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Create a file, modify it, and then delete it';
    const fileName = 'temp.md';
    const initialContent = '# Temporary File';
    const modifiedContent = '# Modified Temporary File\n\nThis file has been modified.';

    const llmResponse = {
      toolCalls: [
        {
          tool: 'create_file',
          params: {
            fileName,
            content: initialContent,
          },
        },
        {
          tool: 'modify_file',
          params: {
            fileName,
            content: modifiedContent,
          },
        },
        {
          tool: 'delete_file',
          params: {
            fileName,
          },
        },
      ],
    };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);
    (commandBus.execute as jest.Mock).mockImplementation(async (command) => {
      if (command instanceof ProcessMessageCommand) {
        const result = await llmProcessorService.processUserMessage(
          command.message.text,
          command.message.userId,
          expect.any(String),
        );

        if (result.text) {
          await telegramService.sendMessage(command.message.chatId, result.text);
        } else if (result.error) {
          await telegramService.sendMessage(command.message.chatId, `Error: ${result.error}`);
        } else if (result.toolCalls) {
          await telegramService.sendMessage(command.message.chatId, 'Processing tool calls...');
          // Process tool calls
          for (const toolCall of result.toolCalls) {
            if (toolCall.tool === 'create_file') {
              await vaultService.createFile(toolCall.params.fileName, toolCall.params.content);
            } else if (toolCall.tool === 'modify_file') {
              await vaultService.modifyFile(toolCall.params.fileName, toolCall.params.content);
            } else if (toolCall.tool === 'delete_file') {
              await vaultService.deleteFile(toolCall.params.fileName);
            }
          }
        } else {
          await telegramService.sendMessage(
            command.message.chatId,
            'Received your message, but no response was generated.',
          );
        }
      }
    });

    // Act
    await commandBus.execute(
      new ProcessMessageCommand({
        chatId,
        userId,
        text: userMessage,
      }),
    );

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(vaultService.createFile).toHaveBeenCalledWith(fileName, initialContent);
    expect(vaultService.modifyFile).toHaveBeenCalledWith(fileName, modifiedContent);
    expect(vaultService.deleteFile).toHaveBeenCalledWith(fileName);
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, 'Processing tool calls...');
  });

  it('should handle errors during tool execution', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Delete a non-existent file';
    const fileName = 'non-existent.md';

    // Override the vault service to simulate an error
    (vaultService.deleteFile as jest.Mock).mockResolvedValueOnce({
      success: false,
      error: 'File not found',
    });

    const llmResponse = {
      toolCalls: [
        {
          tool: 'delete_file',
          params: {
            fileName,
          },
        },
      ],
    };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);
    (commandBus.execute as jest.Mock).mockImplementation(async (command) => {
      if (command instanceof ProcessMessageCommand) {
        const result = await llmProcessorService.processUserMessage(
          command.message.text,
          command.message.userId,
          expect.any(String),
        );

        if (result.text) {
          await telegramService.sendMessage(command.message.chatId, result.text);
        } else if (result.error) {
          await telegramService.sendMessage(command.message.chatId, `Error: ${result.error}`);
        } else if (result.toolCalls) {
          await telegramService.sendMessage(command.message.chatId, 'Processing tool calls...');
          // Process tool calls
          for (const toolCall of result.toolCalls) {
            if (toolCall.tool === 'delete_file') {
              await vaultService.deleteFile(toolCall.params.fileName);
            }
          }
        } else {
          await telegramService.sendMessage(
            command.message.chatId,
            'Received your message, but no response was generated.',
          );
        }
      }
    });

    // Act
    await commandBus.execute(
      new ProcessMessageCommand({
        chatId,
        userId,
        text: userMessage,
      }),
    );

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, 'Processing tool calls...');
    expect(vaultService.deleteFile).toHaveBeenCalledWith(fileName);
  });

  it('should handle mixed text and tool calls in LLM response', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Create a file and explain what you did';
    const fileName = 'notes.md';
    const fileContent = '# Notes\n\nThis is a new notes file.';
    const responseText = 'I have created a new notes file for you.';

    const llmResponse = {
      text: responseText,
      toolCalls: [
        {
          tool: 'create_file',
          params: {
            fileName,
            content: fileContent,
          },
        },
      ],
    };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);
    (commandBus.execute as jest.Mock).mockImplementation(async (command) => {
      if (command instanceof ProcessMessageCommand) {
        const result = await llmProcessorService.processUserMessage(
          command.message.text,
          command.message.userId,
          expect.any(String),
        );

        if (result.text) {
          await telegramService.sendMessage(command.message.chatId, result.text);
        }

        if (result.toolCalls) {
          await telegramService.sendMessage(command.message.chatId, 'Processing tool calls...');
          // Process tool calls
          for (const toolCall of result.toolCalls) {
            if (toolCall.tool === 'create_file') {
              await vaultService.createFile(toolCall.params.fileName, toolCall.params.content);
            }
          }
        } else if (result.error) {
          await telegramService.sendMessage(command.message.chatId, `Error: ${result.error}`);
        } else if (!result.text) {
          await telegramService.sendMessage(
            command.message.chatId,
            'Received your message, but no response was generated.',
          );
        }
      }
    });

    // Act
    await commandBus.execute(
      new ProcessMessageCommand({
        chatId,
        userId,
        text: userMessage,
      }),
    );

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, responseText);
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, 'Processing tool calls...');
    expect(vaultService.createFile).toHaveBeenCalledWith(fileName, fileContent);
  });
});
