import { Test, TestingModule } from '@nestjs/testing';
import { TelegramService } from '../../src/modules/telegram/infrastructure/services/telegram.service';
import { ConfigService } from '../../src/shared/infrastructure/config/config.service';

// Mock the Telegraf class
jest.mock('telegraf', () => {
  return {
    Telegraf: jest.fn().mockImplementation(() => {
      return {
        telegram: {
          sendMessage: jest.fn(),
        },
        launch: jest.fn(),
        stop: jest.fn(),
      };
    }),
  };
});

describe('TelegramService', () => {
  let service: TelegramService;
  let mockBot: any;

  beforeEach(async () => {
    // Setup mock for config service
    const mockConfigService = {
      getTelegramBotToken: jest.fn().mockReturnValue('test-token'),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TelegramService,
        {
          provide: ConfigService,
          useValue: mockConfigService,
        },
      ],
    }).compile();

    service = module.get<TelegramService>(TelegramService);
    mockBot = service.getBot();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('should send a message successfully', async () => {
    // Arrange
    const chatId = 123456789;
    const text = 'Test message';
    mockBot.telegram.sendMessage.mockResolvedValueOnce({});

    // Act
    const result = await service.sendMessage(chatId, text);

    // Assert
    expect(mockBot.telegram.sendMessage).toHaveBeenCalledWith(
      chatId,
      text,
      expect.objectContaining({
        parse_mode: 'Markdown',
      }),
    );
    expect(result).toBe(true);
  });

  it('should sanitize markdown in messages', async () => {
    // Arrange
    const chatId = 123456789;
    const text = 'This is *bold text with unclosed asterisk';
    mockBot.telegram.sendMessage.mockResolvedValueOnce({});

    // Act
    const result = await service.sendMessage(chatId, text);

    // Assert
    expect(mockBot.telegram.sendMessage).toHaveBeenCalledWith(
      chatId,
      'This is *bold text with unclosed asterisk*',
      expect.objectContaining({
        parse_mode: 'Markdown',
      }),
    );
    expect(result).toBe(true);
  });

  it('should fix list items with asterisks', async () => {
    // Arrange
    const chatId = 123456789;
    const text = 'Todo list:\n* Item 1\n* Item 2 with *emphasis*';
    mockBot.telegram.sendMessage.mockResolvedValueOnce({});

    // Act
    const result = await service.sendMessage(chatId, text);

    // Assert
    expect(mockBot.telegram.sendMessage).toHaveBeenCalledWith(
      chatId,
      'Todo list:\n• Item 1\n• Item 2 with *emphasis*',
      expect.objectContaining({
        parse_mode: 'Markdown',
      }),
    );
    expect(result).toBe(true);
  });

  it('should handle the specific error case from the logs', async () => {
    // Arrange
    const chatId = 123456789;
    const problematicText =
      'Исходя из предоставленных данных, на сегодня, 25 апреля 2025 года, у вас запланирована задача:\n\n*   **Кататься на велике с Иваном** (с 19:00 до 22:00). Описание: Покататься на велике с Иваном.\n\nТакже на сегодня была запланирована задача "Заплатить за аренду", но она уже выполнена.';

    mockBot.telegram.sendMessage.mockResolvedValueOnce({});

    // Act
    const result = await service.sendMessage(chatId, problematicText);

    // Assert
    expect(mockBot.telegram.sendMessage).toHaveBeenCalledWith(
      chatId,
      expect.stringContaining('• **Кататься на велике с Иваном**'),
      expect.objectContaining({
        parse_mode: 'Markdown',
      }),
    );
    expect(result).toBe(true);
  });

  it('should fallback to plain text if markdown parsing fails', async () => {
    // Arrange
    const chatId = 123456789;
    const text = 'Some text with *broken markdown';

    // First call fails with an error
    mockBot.telegram.sendMessage.mockRejectedValueOnce(
      new Error("Bad Request: can't parse entities"),
    );
    // Second call (fallback) succeeds
    mockBot.telegram.sendMessage.mockResolvedValueOnce({});

    // Act
    const result = await service.sendMessage(chatId, text);

    // Assert
    // Check that it was called first with markdown
    expect(mockBot.telegram.sendMessage).toHaveBeenCalledWith(
      chatId,
      expect.any(String),
      expect.objectContaining({
        parse_mode: 'Markdown',
      }),
    );

    // Check that it was called again without parse_mode
    expect(mockBot.telegram.sendMessage).toHaveBeenCalledWith(
      chatId,
      text,
      expect.objectContaining({
        parse_mode: undefined,
      }),
    );

    expect(result).toBe(true);
  });
});
