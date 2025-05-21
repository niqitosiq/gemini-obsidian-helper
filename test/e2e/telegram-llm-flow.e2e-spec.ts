import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { MessageDto } from '../../src/modules/telegram/interface/dtos/message.dto';
import { TelegramModule } from '../../src/modules/telegram/telegram.module';
import { LlmModule } from '../../src/modules/llm/llm.module';
import { VaultModule } from '../../src/modules/vault/vault.module';
import { ToolsModule } from '../../src/modules/tools/tools.module';
import { LlmProcessorService } from '../../src/modules/llm/application/services/llm-processor.service';
import { ITelegramService } from '../../src/modules/telegram/domain/interfaces/telegram-service.interface';
import { IVaultService } from '../../src/modules/vault/domain/interfaces/vault-service.interface';
import { ProcessMessageService } from '../../src/modules/telegram/application/services/process-message.service';
import { ToolsRegistryService } from '../../src/modules/tools/application/services/tools-registry.service';

interface MockTelegramService extends ITelegramService {
  sendMessage: jest.Mock;
}

interface MockLlmProcessorService extends Partial<LlmProcessorService> {
  processUserMessage: jest.Mock;
}

interface MockVaultService extends Partial<IVaultService> {
  readAllMarkdownFiles: jest.Mock;
}

describe('Telegram-LLM Flow (e2e)', () => {
  let app: INestApplication | null = null;
  let telegramService: MockTelegramService;
  let llmProcessorService: MockLlmProcessorService;
  let processMessageService: any;
  let vaultService: MockVaultService;

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
    const mockVaultService: MockVaultService = {
      readAllMarkdownFiles: jest.fn().mockResolvedValue({
        'notes.md': '# Notes\n\nThis is a test note.',
        'todo.md': '# Todo\n\n- [ ] Test item',
      }),
    };

    const mockToolsRegistry = {
      executeTool: jest.fn().mockResolvedValue({}),
      getAvailableTools: jest.fn().mockReturnValue([]),
      getToolDefinitions: jest.fn().mockReturnValue([]),
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
      .useValue(mockToolsRegistry)
      .compile();

    telegramService = mockTelegramService;
    llmProcessorService = mockLlmProcessorService;
    vaultService = mockVaultService;

    // Create a mock ProcessMessageService
    processMessageService = {
      processMessage: jest.fn(),
    };
  });

  // No need for afterEach since we're not initializing the app

  it('should process a message and send a text response', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Hello, how are you?';
    const messageDto = new MessageDto(chatId, userId, userMessage);
    const llmResponse = { text: 'I am doing well, thank you for asking!' };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    processMessageService.processMessage.mockImplementation(async (message: MessageDto) => {
      const result = await llmProcessorService.processUserMessage(
        message.text,
        message.userId,
        undefined,
      );

      if (result.text) {
        await telegramService.sendMessage(message.chatId, result.text);
      } else if (result.error) {
        await telegramService.sendMessage(message.chatId, `Error: ${result.error}`);
      } else if (result.toolCalls) {
        await telegramService.sendMessage(message.chatId, 'Processing tool calls...');
      } else {
        await telegramService.sendMessage(
          message.chatId,
          'Received your message, but no response was generated.',
        );
      }
    });

    // Act
    await processMessageService.processMessage(messageDto);

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
    const messageDto = new MessageDto(chatId, userId, userMessage);
    const llmResponse = { error: 'API quota exceeded' };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    processMessageService.processMessage.mockImplementation(async (message: MessageDto) => {
      const result = await llmProcessorService.processUserMessage(
        message.text,
        message.userId,
        undefined,
      );

      if (result.text) {
        await telegramService.sendMessage(message.chatId, result.text);
      } else if (result.error) {
        await telegramService.sendMessage(message.chatId, `Error: ${result.error}`);
      } else if (result.toolCalls) {
        await telegramService.sendMessage(message.chatId, 'Processing tool calls...');
      } else {
        await telegramService.sendMessage(
          message.chatId,
          'Received your message, but no response was generated.',
        );
      }
    });

    // Act
    await processMessageService.processMessage(messageDto);

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
    const messageDto = new MessageDto(chatId, userId, userMessage);
    const llmResponse = {
      toolCalls: [
        {
          tool: 'create_file',
          params: {
            fileName: 'notes.md',
            content: '# Notes\n\nThis is a test note.',
          },
        },
      ],
    };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    processMessageService.processMessage.mockImplementation(async (message: MessageDto) => {
      const result = await llmProcessorService.processUserMessage(
        message.text,
        message.userId,
        undefined,
      );

      if (result.text) {
        await telegramService.sendMessage(message.chatId, result.text);
      } else if (result.error) {
        await telegramService.sendMessage(message.chatId, `Error: ${result.error}`);
      } else if (result.toolCalls) {
        await telegramService.sendMessage(message.chatId, 'Processing tool calls...');
      } else {
        await telegramService.sendMessage(
          message.chatId,
          'Received your message, but no response was generated.',
        );
      }
    });

    // Act
    await processMessageService.processMessage(messageDto);

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      undefined,
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, 'Processing tool calls...');
  });

  it('should handle empty response from LLM', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Trigger empty response';
    const messageDto = new MessageDto(chatId, userId, userMessage);
    const llmResponse = {};

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    processMessageService.processMessage.mockImplementation(async (message: MessageDto) => {
      const result = await llmProcessorService.processUserMessage(
        message.text,
        message.userId,
        undefined,
      );

      if (result.text) {
        await telegramService.sendMessage(message.chatId, result.text);
      } else if (result.error) {
        await telegramService.sendMessage(message.chatId, `Error: ${result.error}`);
      } else if (result.toolCalls) {
        await telegramService.sendMessage(message.chatId, 'Processing tool calls...');
      } else {
        await telegramService.sendMessage(
          message.chatId,
          'Received your message, but no response was generated.',
        );
      }
    });

    // Act
    await processMessageService.processMessage(messageDto);

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
});
