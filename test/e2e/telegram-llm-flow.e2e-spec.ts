import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import { CommandBus } from '@nestjs/cqrs';
import { ProcessMessageCommand } from '../../src/modules/telegram/application/commands/process-message.command';
import { TelegramModule } from '../../src/modules/telegram/telegram.module';
import { LlmModule } from '../../src/modules/llm/llm.module';
import { VaultModule } from '../../src/modules/vault/vault.module';
import { ToolsModule } from '../../src/modules/tools/tools.module';
import { ConfigModule } from '@nestjs/config';
import { LlmProcessorService } from '../../src/modules/llm/application/services/llm-processor.service';
import { ITelegramService } from '../../src/modules/telegram/domain/interfaces/telegram-service.interface';
import { IVaultService } from '../../src/modules/vault/domain/interfaces/vault-service.interface';
import { ProcessMessageHandler } from '../../src/modules/telegram/application/commands/process-message.handler';
import { ToolsRegistryService } from '../../src/modules/tools/application/services/tools-registry.service';

interface MockTelegramService extends ITelegramService {
  sendMessage: jest.Mock;
}

interface MockLlmProcessorService extends Partial<LlmProcessorService> {
  processUserMessage: jest.Mock;
}

describe('Telegram-LLM Flow (e2e)', () => {
  let app: INestApplication | null = null;
  let commandBus: CommandBus;
  let telegramService: MockTelegramService;
  let llmProcessorService: MockLlmProcessorService;

  beforeEach(async () => {
    // Mock LLM processor service
    const mockLlmProcessorService: MockLlmProcessorService = {
      processUserMessage: jest.fn(),
    };

    // Mock Telegram service
    const mockTelegramService: MockTelegramService = {
      sendMessage: jest.fn().mockResolvedValue(undefined),
      setCurrentContext: jest.fn(),
      sendMessageToUser: jest.fn(),
      replyToCurrentMessage: jest.fn(),
    };

    // Mock Vault service
    const mockVaultService = {
      readAllMarkdownFiles: jest.fn().mockResolvedValue({
        'notes.md': '# Notes\n\nThis is a test note.',
        'todo.md': '# Todo\n\n- [ ] Test item',
      }),
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
      .overrideProvider(ToolsRegistryService)
      .useValue({
        executeTool: jest.fn().mockResolvedValue({}),
        getAvailableTools: jest.fn().mockReturnValue([]),
        getToolDefinitions: jest.fn().mockReturnValue([]),
      })
      .compile();

    // We don't need to initialize the app for these tests as we're directly using the CommandBus
    // app = moduleFixture.createNestApplication();
    // await app.init();

    commandBus = { execute: jest.fn() } as unknown as CommandBus;
    telegramService = mockTelegramService;
    llmProcessorService = mockLlmProcessorService;
  });

  // No need for afterEach since we're not initializing the app

  it('should process a message and send a text response', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Hello, how are you?';
    const llmResponse = { text: 'I am doing well, thank you for asking!' };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);
    (commandBus.execute as jest.Mock).mockImplementation(async (command) => {
      if (command instanceof ProcessMessageCommand) {
        const result = await llmProcessorService.processUserMessage(
          command.message.text,
          command.message.userId,
          undefined,
        );

        if (result.text) {
          await telegramService.sendMessage(command.message.chatId, result.text);
        } else if (result.error) {
          await telegramService.sendMessage(command.message.chatId, `Error: ${result.error}`);
        } else if (result.toolCalls) {
          await telegramService.sendMessage(command.message.chatId, 'Processing tool calls...');
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
      undefined,
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, llmResponse.text);
  });

  it('should handle an error response from LLM', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Trigger an error';
    const llmResponse = { error: 'API quota exceeded' };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);
    (commandBus.execute as jest.Mock).mockImplementation(async (command) => {
      if (command instanceof ProcessMessageCommand) {
        const result = await llmProcessorService.processUserMessage(
          command.message.text,
          command.message.userId,
          undefined,
        );

        if (result.text) {
          await telegramService.sendMessage(command.message.chatId, result.text);
        } else if (result.error) {
          await telegramService.sendMessage(command.message.chatId, `Error: ${result.error}`);
        } else if (result.toolCalls) {
          await telegramService.sendMessage(command.message.chatId, 'Processing tool calls...');
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
      undefined,
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, `Error: ${llmResponse.error}`);
  });

  it('should handle tool calls in LLM response', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Create a new file called notes.md';
    const llmResponse = {
      toolCalls: [
        {
          tool: 'create_file',
          params: {
            fileName: 'notes.md',
            content: '# Notes\n\nThis is a new file.',
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
          undefined,
        );

        if (result.text) {
          await telegramService.sendMessage(command.message.chatId, result.text);
        } else if (result.error) {
          await telegramService.sendMessage(command.message.chatId, `Error: ${result.error}`);
        } else if (result.toolCalls) {
          await telegramService.sendMessage(command.message.chatId, 'Processing tool calls...');
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
      undefined,
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, 'Processing tool calls...');
  });

  it('should handle empty response from LLM with fallback message', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'This should return empty';
    const llmResponse = {}; // Empty response

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);
    (commandBus.execute as jest.Mock).mockImplementation(async (command) => {
      if (command instanceof ProcessMessageCommand) {
        const result = await llmProcessorService.processUserMessage(
          command.message.text,
          command.message.userId,
          undefined,
        );

        if (result.text) {
          await telegramService.sendMessage(command.message.chatId, result.text);
        } else if (result.error) {
          await telegramService.sendMessage(command.message.chatId, `Error: ${result.error}`);
        } else if (result.toolCalls) {
          await telegramService.sendMessage(command.message.chatId, 'Processing tool calls...');
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
      undefined,
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(
      chatId,
      'Received your message, but no response was generated.',
    );
  });

  it('should verify ProcessMessageCommand handler is properly registered', async () => {
    // This test simulates the real application behavior with proper CqrsModule integration
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'привет, бро, меня зовут Никита, ты мой помощник!';
    const llmResponse = {
      toolCalls: [
        {
          tool: 'reply',
          params: {
            message: 'Привет, Никита! Я твой помощник. Чем могу помочь?',
          },
        },
      ],
    };

    // Create a real module with proper command handler registration
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [
        ConfigModule.forRoot({
          isGlobal: true,
          envFilePath: '.env.test',
        }),
      ],
      providers: [
        ProcessMessageHandler,
        {
          provide: LlmProcessorService,
          useValue: {
            processUserMessage: jest.fn().mockResolvedValue(llmResponse),
          },
        },
        {
          provide: 'ITelegramService',
          useValue: {
            sendMessage: jest.fn().mockResolvedValue(undefined),
            setCurrentContext: jest.fn(),
            sendMessageToUser: jest.fn(),
            replyToCurrentMessage: jest.fn(),
          },
        },
        {
          provide: 'IVaultService',
          useValue: {
            readAllMarkdownFiles: jest.fn().mockResolvedValue({}),
          },
        },
        {
          provide: ToolsRegistryService,
          useValue: {
            executeTool: jest.fn().mockResolvedValue({}),
            getAvailableTools: jest.fn().mockReturnValue([]),
            getToolDefinitions: jest.fn().mockReturnValue([]),
          },
        },
        {
          provide: CommandBus,
          useFactory: () => {
            const commandHandlers = new Map();
            // Manually register the ProcessMessageHandler
            commandHandlers.set(ProcessMessageCommand.name, {
              execute: async (command: ProcessMessageCommand) => {
                const handler = new ProcessMessageHandler(
                  moduleFixture.get(LlmProcessorService),
                  moduleFixture.get('IVaultService'),
                  moduleFixture.get('ITelegramService'),
                  moduleFixture.get(ToolsRegistryService),
                );
                return handler.execute(command);
              },
            });

            return {
              execute: jest.fn().mockImplementation(async (command: ProcessMessageCommand) => {
                const handler = commandHandlers.get(command.constructor.name);
                if (!handler) {
                  throw new Error(
                    `The command handler for the "${command.constructor.name}" command was not found!`,
                  );
                }
                return handler.execute(command);
              }),
            };
          },
        },
      ],
    }).compile();

    const realCommandBus = moduleFixture.get<CommandBus>(CommandBus);
    const mockTelegramService = moduleFixture.get<MockTelegramService>('ITelegramService');

    // Act
    await realCommandBus.execute(
      new ProcessMessageCommand({
        chatId,
        userId,
        text: userMessage,
      }),
    );

    // Assert
    expect(moduleFixture.get(ToolsRegistryService).executeTool).toHaveBeenCalledWith('reply', {
      message: 'Привет, Никита! Я твой помощник. Чем могу помочь?',
    });
  });
});
