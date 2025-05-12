import { Test, TestingModule } from '@nestjs/testing';
import { ConfigService } from '@nestjs/config';
import { LlmProcessorService } from '../../src/modules/llm/application/services/llm-processor.service';
import { ToolsRegistryService } from '../../src/modules/tools/application/services/tools-registry.service';
import { GoogleGenaiAdapter } from '../../src/modules/llm/infrastructure/adapters/google-genai.adapter';

describe('LlmProcessorService', () => {
  let service: LlmProcessorService;
  let mockToolsRegistry: Partial<ToolsRegistryService>;
  let mockGoogleGenaiAdapter: Partial<GoogleGenaiAdapter>;

  beforeEach(async () => {
    // Reset mocks
    jest.clearAllMocks();

    // Setup mock for tools registry
    mockToolsRegistry = {
      getAvailableTools: jest.fn().mockReturnValue(['create_file', 'modify_file', 'delete_file']),
      executeTool: jest.fn(),
    };

    // Setup mock for GoogleGenaiAdapter
    mockGoogleGenaiAdapter = {
      generateContent: jest.fn(),
    };

    // Setup mock for config service
    const mockConfigService = {
      get: jest.fn().mockImplementation((key) => {
        if (key === 'GEMINI_API_KEY') return 'test-api-key';
        return undefined;
      }),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        LlmProcessorService,
        {
          provide: ConfigService,
          useValue: mockConfigService,
        },
        {
          provide: ToolsRegistryService,
          useValue: mockToolsRegistry,
        },
        {
          provide: GoogleGenaiAdapter,
          useValue: mockGoogleGenaiAdapter,
        },
      ],
    }).compile();

    service = module.get<LlmProcessorService>(LlmProcessorService);
  });

  it('should process a message and return plain text response', async () => {
    // Arrange
    const userId = 123;
    const message = 'Hello, how are you?';
    const expectedResponse = 'I am an AI assistant. How can I help you?';

    (mockGoogleGenaiAdapter.generateContent as jest.Mock).mockResolvedValue({
      text: expectedResponse,
    });

    // Act
    const result = await service.processUserMessage(message, userId);

    // Assert
    expect(mockGoogleGenaiAdapter.generateContent).toHaveBeenCalled();
    expect(result).toEqual({
      text: expectedResponse,
    });
  });

  it('should include vault context when provided', async () => {
    // Arrange
    const userId = 123;
    const message = 'What files do I have?';
    const vaultContext = 'File: notes.md\n\n```\n# Notes\nThis is a note.\n```\n\n';
    const expectedResponse =
      'You have a notes.md file with a heading "Notes" and content "This is a note."';

    (mockGoogleGenaiAdapter.generateContent as jest.Mock).mockResolvedValue({
      text: expectedResponse,
    });

    // Act
    const result = await service.processUserMessage(message, userId, vaultContext);

    // Assert
    expect(mockGoogleGenaiAdapter.generateContent).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({
          text: expect.stringContaining('Context from vault:'),
        }),
      ]),
    );
    expect(result).toEqual({
      text: expectedResponse,
    });
  });

  it('should detect and extract tool calls from LLM response', async () => {
    // Arrange
    const userId = 123;
    const message = 'Create a new file called todo.md';
    const responseWithToolCall = `I'll create that file for you.

[[tool:create_file]]{"fileName":"todo.md","content":"# Todo List\\n\\n- [ ] First task\\n- [ ] Second task"}[[/tool]]`;

    (mockGoogleGenaiAdapter.generateContent as jest.Mock).mockResolvedValue({
      text: responseWithToolCall,
    });

    // Act
    const result = await service.processUserMessage(message, userId);

    // Assert
    expect(mockGoogleGenaiAdapter.generateContent).toHaveBeenCalled();
    expect(result).toHaveProperty('toolCalls');
    expect(result.toolCalls?.length).toBe(1);
    expect(result.toolCalls?.[0]).toEqual({
      tool: 'create_file',
      params: {
        fileName: 'todo.md',
        content: '# Todo List\n\n- [ ] First task\n- [ ] Second task',
      },
    });
  });

  it('should handle multiple tool calls in a single response', async () => {
    // Arrange
    const userId = 123;
    const message = 'Create two files: todo.md and notes.md';
    const responseWithMultipleToolCalls = `I'll create those files for you.

[[tool:create_file]]{"fileName":"todo.md","content":"# Todo List\\n\\n- [ ] Task 1"}[[/tool]]
[[tool:create_file]]{"fileName":"notes.md","content":"# Notes\\n\\nImportant notes here."}[[/tool]]`;

    (mockGoogleGenaiAdapter.generateContent as jest.Mock).mockResolvedValue({
      text: responseWithMultipleToolCalls,
    });

    // Act
    const result = await service.processUserMessage(message, userId);

    // Assert
    expect(mockGoogleGenaiAdapter.generateContent).toHaveBeenCalled();
    expect(result).toHaveProperty('toolCalls');
    expect(result.toolCalls?.length).toBe(2);

    if (result.toolCalls && result.toolCalls.length >= 2) {
      expect(result.toolCalls[0].tool).toBe('create_file');
      expect(result.toolCalls[1].tool).toBe('create_file');
      expect(result.toolCalls[0].params.fileName).toBe('todo.md');
      expect(result.toolCalls[1].params.fileName).toBe('notes.md');
    }
  });

  it('should handle errors from the LLM API', async () => {
    // Arrange
    const userId = 123;
    const message = 'Hello';
    const errorMessage = 'API quota exceeded';

    (mockGoogleGenaiAdapter.generateContent as jest.Mock).mockRejectedValue(
      new Error(errorMessage),
    );

    // Act
    const result = await service.processUserMessage(message, userId);

    // Assert
    expect(mockGoogleGenaiAdapter.generateContent).toHaveBeenCalled();
    expect(result).toEqual({
      error: errorMessage,
    });
  });

  it('should handle null response from the adapter', async () => {
    // Arrange
    const userId = 123;
    const message = 'Hello';

    (mockGoogleGenaiAdapter.generateContent as jest.Mock).mockResolvedValue(null);

    // Act
    const result = await service.processUserMessage(message, userId);

    // Assert
    expect(mockGoogleGenaiAdapter.generateContent).toHaveBeenCalled();
    expect(result).toEqual({
      error: 'Failed to generate content from LLM',
    });
  });

  it('should handle malformed tool call JSON in response', async () => {
    // Arrange
    const userId = 123;
    const message = 'Create a file with invalid JSON';
    const responseWithInvalidToolCall = `I'll try to create that file.

[[tool:create_file]]{"fileName":"invalid.md","content: "Missing quote}[[/tool]]`;

    (mockGoogleGenaiAdapter.generateContent as jest.Mock).mockResolvedValue({
      text: responseWithInvalidToolCall,
    });

    // Act
    const result = await service.processUserMessage(message, userId);

    // Assert
    expect(mockGoogleGenaiAdapter.generateContent).toHaveBeenCalled();
    expect(result).toHaveProperty('text');
    // expect(result.text).toBe(responseWithInvalidToolCall);
    expect(result).not.toHaveProperty('toolCalls');
  });
});
