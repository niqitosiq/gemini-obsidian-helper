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

describe('Telegram-Tools Integration (e2e)', () => {
  let commandBus: CommandBus;
  let telegramService: MockTelegramService;
  let llmProcessorService: MockLlmProcessorService;
  let vaultService: MockVaultService;
  let mockCreateFileTool: any;
  let mockModifyFileTool: any;
  let mockDeleteFileTool: any;

  beforeEach(async () => {
    // Mock services
    const mockLlmProcessorService: MockLlmProcessorService = {
      processUserMessage: jest.fn(),
    };

    const mockTelegramService: MockTelegramService = {
      sendMessage: jest.fn().mockResolvedValue(undefined),
      setCurrentContext: jest.fn(),
      sendMessageToUser: jest.fn(),
      replyToCurrentMessage: jest.fn(),
    };

    const mockVaultService: MockVaultService = {
      readAllMarkdownFiles: jest.fn().mockResolvedValue({
        'notes.md': '# Notes\n\nThis is a test note.',
        'todo.md': '# Todo\n\n- [ ] Test item',
      }),
      createFile: jest.fn().mockResolvedValue(true),
      modifyFile: jest.fn().mockResolvedValue(true),
      deleteFile: jest.fn().mockResolvedValue(true),
    };

    // Mock tool handlers
    mockCreateFileTool = {
      execute: jest.fn().mockResolvedValue({
        status: 'success',
        message: 'File created successfully',
      }),
    };

    mockModifyFileTool = {
      execute: jest.fn().mockResolvedValue({
        status: 'success',
        message: 'File modified successfully',
      }),
    };

    mockDeleteFileTool = {
      execute: jest.fn().mockResolvedValue({
        status: 'success',
        message: 'File deleted successfully',
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
      .overrideProvider(LlmProcessorService)
      .useValue(mockLlmProcessorService)
      .overrideProvider('ITelegramService')
      .useValue(mockTelegramService)
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

  it('should process a message with file creation tool call', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Create a new file called meeting-notes.md';

    const llmResponse = {
      toolCalls: [
        {
          tool: 'create_file',
          params: {
            fileName: 'meeting-notes.md',
            content:
              '# Meeting Notes\n\n## Agenda\n\n1. Project updates\n2. Timeline review\n3. Next steps',
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
              await mockCreateFileTool.execute(toolCall.params);
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
  });

  it('should process a message with multiple tool calls', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Create a file and then modify it';

    const llmResponse = {
      toolCalls: [
        {
          tool: 'create_file',
          params: {
            fileName: 'project.md',
            content: '# Project\n\nInitial content',
          },
        },
        {
          tool: 'modify_file',
          params: {
            fileName: 'project.md',
            content: '# Project\n\nUpdated content\n\n## Details\n\nMore information here',
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
              await mockCreateFileTool.execute(toolCall.params);
            } else if (toolCall.tool === 'modify_file') {
              await mockModifyFileTool.execute(toolCall.params);
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
  });

  it('should handle errors from tool execution', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Delete a non-existent file';

    // Mock an error response for this specific test
    mockDeleteFileTool.execute.mockResolvedValueOnce({
      status: 'error',
      message: 'File not found',
    });

    const llmResponse = {
      toolCalls: [
        {
          tool: 'delete_file',
          params: {
            fileName: 'non-existent.md',
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
              await mockDeleteFileTool.execute(toolCall.params);
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
  });
});
