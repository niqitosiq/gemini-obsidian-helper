import { Test, TestingModule } from '@nestjs/testing';
import { CommandBus, CqrsModule } from '@nestjs/cqrs';
import { ConfigModule } from '@nestjs/config';
import { ProcessMessageCommand } from '../../src/modules/telegram/application/commands/process-message.command';
import { ProcessMessageHandler } from '../../src/modules/telegram/application/commands/process-message.handler';
import { LlmProcessorService } from '../../src/modules/llm/application/services/llm-processor.service';
import { ToolsRegistryService } from '../../src/modules/tools/application/services/tools-registry.service';

describe('CommandBus Registration', () => {
  let commandBus: CommandBus;
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
        CqrsModule,
        ConfigModule.forRoot({
          isGlobal: true,
          envFilePath: '.env.test',
        }),
      ],
      providers: [
        ProcessMessageHandler,
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
      ],
    }).compile();

    commandBus = moduleFixture.get<CommandBus>(CommandBus);
    llmProcessorService = moduleFixture.get<LlmProcessorService>(LlmProcessorService);
    telegramService = moduleFixture.get('ITelegramService');
    vaultService = moduleFixture.get('IVaultService');
    toolsRegistry = moduleFixture.get(ToolsRegistryService);

    // Register the command handler manually
    commandBus.register([ProcessMessageHandler]);
  });

  it('should handle ProcessMessageCommand correctly', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'привет, бро, меня зовут Никита, ты мой помощник!';

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
    expect(toolsRegistry.executeTool).toHaveBeenCalledWith('reply', { message: 'Test response' });
  });
});
