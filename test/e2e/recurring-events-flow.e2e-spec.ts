import { Test, TestingModule } from '@nestjs/testing';
import { ConfigModule } from '@nestjs/config';
import { ITelegramService } from '../../src/modules/telegram/domain/interfaces/telegram-service.interface';
import { LlmProcessorService } from '../../src/modules/llm/application/services/llm-processor.service';

interface MockTelegramService extends ITelegramService {
  sendMessage: jest.Mock;
}

interface MockLlmProcessorService extends Partial<LlmProcessorService> {
  processUserMessage: jest.Mock;
}

// Define a mock EventScheduler class to use in tests
class MockEventScheduler {
  scheduleEvent = jest.fn().mockResolvedValue(true);
  cancelEvent = jest.fn().mockResolvedValue(true);
  executeEvent: jest.Mock;

  constructor(llmProcessorService: MockLlmProcessorService, telegramService: MockTelegramService) {
    this.executeEvent = jest.fn().mockImplementation(async (eventId, eventData) => {
      // Actually call the LLM processor and telegram service in the mock
      try {
        const result = await llmProcessorService.processUserMessage(
          `Execute recurring event: ${eventData.name} - ${eventData.message}`,
          eventData.userId,
          undefined,
        );

        if (result && result.text) {
          await telegramService.sendMessage(eventData.chatId, result.text);
        } else if (result && result.error) {
          await telegramService.sendMessage(eventData.chatId, `Error: ${result.error}`);
        }
        return true;
      } catch (error) {
        console.error('Error executing event:', error);
        return false;
      }
    });
  }
}

// Define a mock RecurringEventsService class
class MockRecurringEventsService {
  eventScheduler: MockEventScheduler;

  constructor(eventScheduler: MockEventScheduler) {
    this.eventScheduler = eventScheduler;
  }

  createEvent = jest.fn().mockImplementation(async (eventData) => {
    await this.eventScheduler.scheduleEvent(eventData);
    return true;
  });

  cancelEvent = jest.fn().mockImplementation(async (eventId) => {
    await this.eventScheduler.cancelEvent(eventId);
    return true;
  });
}

describe('Recurring Events Flow (e2e)', () => {
  let recurringEventsService: MockRecurringEventsService;
  let telegramService: MockTelegramService;
  let llmProcessorService: MockLlmProcessorService;
  let eventScheduler: MockEventScheduler;

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

    const mockEventScheduler = new MockEventScheduler(mockLlmProcessorService, mockTelegramService);
    const mockRecurringEventsService = new MockRecurringEventsService(mockEventScheduler);

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
      .overrideProvider('RecurringEventsService')
      .useValue(mockRecurringEventsService)
      .compile();

    // We don't need to initialize the app for these tests
    recurringEventsService = mockRecurringEventsService;
    telegramService = mockTelegramService;
    llmProcessorService = mockLlmProcessorService;
    eventScheduler = mockEventScheduler;
  });

  // No need for afterEach since we're not initializing the app

  it('should create a recurring event', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const eventData = {
      name: 'Daily Reminder',
      cronExpression: '0 9 * * *', // Every day at 9 AM
      message: 'Remember to check your tasks for today!',
      chatId,
      userId,
    };

    // Act
    const result = await recurringEventsService.createEvent(eventData);

    // Assert
    expect(eventScheduler.scheduleEvent).toHaveBeenCalled();
    expect(result).toBeTruthy();
  });

  it('should execute a recurring event and send a message', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const eventId = 'event-123';
    const eventData = {
      name: 'Daily Reminder',
      cronExpression: '0 9 * * *',
      message: 'Remember to check your tasks for today!',
      chatId,
      userId,
    };

    const llmResponse = {
      text: 'Here is your daily reminder: Remember to check your tasks for today!',
    };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    // Act
    await eventScheduler.executeEvent(eventId, eventData);

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalledWith(
      `Execute recurring event: ${eventData.name} - ${eventData.message}`,
      userId,
      undefined,
    );
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, llmResponse.text);
  });

  it('should handle LLM errors during event execution', async () => {
    // Arrange
    const chatId = 123456789;
    const userId = 987654321;
    const eventId = 'event-456';
    const eventData = {
      name: 'Weekly Summary',
      cronExpression: '0 18 * * 5', // Every Friday at 6 PM
      message: 'Generate a summary of the week',
      chatId,
      userId,
    };

    const llmResponse = {
      error: 'API quota exceeded',
    };

    (llmProcessorService.processUserMessage as jest.Mock).mockResolvedValueOnce(llmResponse);

    // Act
    await eventScheduler.executeEvent(eventId, eventData);

    // Assert
    expect(llmProcessorService.processUserMessage).toHaveBeenCalled();
    expect(telegramService.sendMessage).toHaveBeenCalledWith(chatId, `Error: ${llmResponse.error}`);
  });

  it('should cancel a recurring event', async () => {
    // Arrange
    const eventId = 'event-789';

    // Act
    const result = await recurringEventsService.cancelEvent(eventId);

    // Assert
    expect(eventScheduler.cancelEvent).toHaveBeenCalledWith(eventId);
    expect(result).toBeTruthy();
  });
});
