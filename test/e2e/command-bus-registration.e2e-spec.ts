import { Test, TestingModule } from '@nestjs/testing';
import { ConfigModule } from '@nestjs/config';
import { MessageDto } from '../../src/modules/telegram/interface/dtos/message.dto';
import { ProcessMessageService } from '../../src/modules/telegram/application/services/process-message.service';
import { LlmProcessorService } from '../../src/modules/llm/application/services/llm-processor.service';
import { ToolsRegistryService } from '../../src/modules/tools/application/services/tools-registry.service';

describe('ProcessMessage Service', () => {
  let processMessageService: ProcessMessageService;
  let llmProcessorService: LlmProcessorService;
  let telegramService: any;
  let vaultService: any;
  let toolsRegistry: any;

  beforeEach(async () => {
    // Mock services
    const mockLlmProcessorService = {
      processUserMessage: jest.fn().mockResolvedValue({
        toolCalls: [
          {
            tool: 'reply',
            params: {
              message: 'Test response',
            },
          },
        ],
      }),
    };

    const mockTelegramService = {
      sendMessage: jest.fn().mockResolvedValue(undefined),
    };

    const mockVaultService = {
      readAllMarkdownFiles: jest.fn().mockResolvedValue({}),
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
      providers: [
        ProcessMessageService,
        {
          provide: LlmProcessorService,
          useValue: mockLlmProcessorService,
        },
        {
          provide: 'ITelegramService',
          useValue: mockTelegramService,
        },
        {
          provide: 'IVaultService',
          useValue: mockVaultService,
        },
        {
          provide: ToolsRegistryService,
          useValue: mockToolsRegistry,
        },
        {
          provide: 'VaultService',
          useValue: mockVaultService,
        },
      ],
    }).compile();

    processMessageService = moduleFixture.get<ProcessMessageService>(ProcessMessageService);
    llmProcessorService = moduleFixture.get<LlmProcessorService>(LlmProcessorService);
    telegramService = moduleFixture.get('ITelegramService');
    vaultService = moduleFixture.get('IVaultService');
    toolsRegistry = moduleFixture.get(ToolsRegistryService);
  });

  it('should handle message processing correctly', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'привет, бро, меня зовут Никита, ты мой помощник!';
    const messageDto = new MessageDto(chatId, userId, userMessage);

    // Act
    await processMessageService.processMessage(messageDto);

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      undefined,
    );
    expect(toolsRegistry.executeTool).toHaveBeenCalledWith('reply', { message: 'Test response' });
  });
});
