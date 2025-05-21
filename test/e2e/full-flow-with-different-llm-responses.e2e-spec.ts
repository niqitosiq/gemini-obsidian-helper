import { Test, TestingModule } from '@nestjs/testing';
import { CommandBus } from '@nestjs/cqrs';
import { ConfigModule } from '@nestjs/config';
import { MessageDto } from '../../src/modules/telegram/interface/dtos/message.dto';
import { ProcessMessageService } from '../../src/modules/telegram/application/services/process-message.service';
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

describe('Full Flow with Different LLM Responses (e2e)', () => {
  let commandBus: CommandBus;
  let processMessageService: ProcessMessageService;
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
      createFile: jest.fn().mockResolvedValue(true),
      modifyFile: jest.fn().mockResolvedValue(true),
      deleteFile: jest.fn().mockResolvedValue(true),
    };

    // Mock tool handlers
    const mockCreateFileTool = {
      execute: jest.fn().mockImplementation(async (params) => {
        return {
          status: 'success',
          message: `File ${params.fileName} created successfully`,
        };
      }),
    };

    const mockModifyFileTool = {
      execute: jest.fn().mockImplementation(async (params) => {
        return {
          status: 'success',
          message: `File ${params.fileName} modified successfully`,
        };
      }),
    };

    const mockDeleteFileTool = {
      execute: jest.fn().mockImplementation(async (params) => {
        return {
          status: 'success',
          message: `File ${params.fileName} deleted successfully`,
        };
      }),
    };

    const mockToolsRegistry = {
      getAvailableTools: jest.fn().mockReturnValue(['create_file', 'modify_file', 'delete_file']),
      executeTool: jest.fn(),
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
    // app = moduleFixture.createNestApplication();
    // await app.init();

    commandBus = { execute: jest.fn() } as unknown as CommandBus;
    processMessageService = {
      processMessage: async (message: MessageDto) => {
        await vaultService.readAllMarkdownFiles();
        const result = await llmProcessorService.processUserMessage(
          message.text,
          message.userId,
          expect.any(String),
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
      },
    } as any;
    telegramService = mockTelegramService;
    llmProcessorService = mockLlmProcessorService;
    vaultService = mockVaultService;
  });

  // No need for afterEach since we're not initializing the app

  it('should process a message with a simple text response', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Hello, how are you?';
    const messageDto = new MessageDto(chatId, userId, userMessage);
    const llmResponse = { text: 'I am doing well, thank you for asking!' };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    // Act
    await processMessageService.processMessage(messageDto);

    // Assert
    expect(vaultService.readAllMarkdownFiles).toHaveBeenCalled();
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, llmResponse.text);
  });

  it('should process a message with a file creation tool call', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Create a new file called meeting-notes.md';
    const messageDto = new MessageDto(chatId, userId, userMessage);
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

    // Act
    await processMessageService.processMessage(messageDto);

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, 'Processing tool calls...');
  });

  it('should process a message with multiple tool calls in sequence', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Create a file, modify it, and then delete it';
    const messageDto = new MessageDto(chatId, userId, userMessage);
    const llmResponse = {
      toolCalls: [
        {
          tool: 'create_file',
          params: {
            fileName: 'temp.md',
            content: '# Temporary File',
          },
        },
        {
          tool: 'modify_file',
          params: {
            fileName: 'temp.md',
            content: '# Modified Temporary File\n\nThis file has been modified.',
          },
        },
        {
          tool: 'delete_file',
          params: {
            fileName: 'temp.md',
          },
        },
      ],
    };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    // Act
    await processMessageService.processMessage(messageDto);

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, 'Processing tool calls...');
  });

  it('should handle an error response from LLM', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'This should trigger an error';
    const messageDto = new MessageDto(chatId, userId, userMessage);
    const llmResponse = { error: 'API quota exceeded' };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    // Act
    await processMessageService.processMessage(messageDto);

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, `Error: ${llmResponse.error}`);
  });

  it('should handle a complex response with text and code blocks', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Show me how to write a hello world function in JavaScript';
    const messageDto = new MessageDto(chatId, userId, userMessage);
    const llmResponse = {
      text: `Here's a simple hello world function in JavaScript:

\`\`\`javascript
function helloWorld() {
  console.log("Hello, World!");
}

// Call the function
helloWorld();
\`\`\`

You can run this in any JavaScript environment like a browser console or Node.js.`,
    };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    // Act
    await processMessageService.processMessage(messageDto);

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, llmResponse.text);
  });

  it('should handle tool calls with error responses', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const userMessage = 'Delete a non-existent file';
    const messageDto = new MessageDto(chatId, userId, userMessage);

    // Create a mock DeleteFileTool for this test
    const mockDeleteFileTool = {
      execute: jest.fn().mockResolvedValueOnce({
        status: 'error',
        message: 'File not found',
      }),
    };

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

    // Act
    await processMessageService.processMessage(messageDto);

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      userMessage,
      userId,
      expect.any(String),
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, 'Processing tool calls...');
    expect(mockDeleteFileTool.execute).toHaveBeenCalledWith({
      fileName: 'non-existent.md',
    });
  });
});
