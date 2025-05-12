import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { TelegramService } from '../../infrastructure/services/telegram.service';
import { CommandBus } from '@nestjs/cqrs';
import { ProcessMessageCommand } from '../commands/process-message.command';
import { MessageDto } from '../../interface/dtos/message.dto';
import { ConfigService } from '../../../../shared/infrastructure/config/config.service';
import { ProcessMessageHandler } from '../commands/process-message.handler';

@Injectable()
export class TelegramAppService implements OnModuleInit, OnModuleDestroy {
  private allowedUserIds: number[] = [];

  constructor(
    private readonly telegramService: TelegramService,
    private readonly commandBus: CommandBus,
    private readonly configService: ConfigService,
    private readonly processMessageHandler: ProcessMessageHandler,
  ) {
    // Get allowed user IDs from config
    const userIds = this.configService.getTelegramUserIds();
    this.allowedUserIds = userIds.map((id) => parseInt(id, 10)).filter((id) => !isNaN(id));
  }

  async onModuleInit(): Promise<void> {
    const bot = this.telegramService.getBot();

    // Set up message handler
    bot.on('message', async (ctx) => {
      const userId = ctx.from?.id;

      // Check if user is allowed
      if (!userId || !this.allowedUserIds.includes(userId)) {
        console.log(`Unauthorized access attempt from user ID: ${userId}`);
        return;
      }

      // Set current context for potential direct replies
      this.telegramService.setCurrentContext(ctx.update, ctx);

      // Process text messages
      if (ctx.message && 'text' in ctx.message && ctx.message.text) {
        const chatId = ctx.chat.id;
        const text = ctx.message.text;

        // Create DTO and dispatch command
        const messageDto = new MessageDto(chatId, userId, text);

        try {
          // Use the handler directly instead of the CommandBus
          await this.processMessageHandler.execute(new ProcessMessageCommand(messageDto));
        } catch (error) {
          console.error('Error processing message:', error);
          await ctx.reply('Sorry, there was an error processing your message.');
        }
      }

      // Process voice messages
      else if (ctx.message && 'voice' in ctx.message && ctx.message.voice) {
        // In a full implementation, we would handle voice messages here
        // by downloading the file and transcribing it
        await ctx.reply('Voice message processing is not implemented yet.');
      }
    });

    // Set up command handlers
    bot.command('start', async (ctx) => {
      const userId = ctx.from?.id;

      // Check if user is allowed
      if (!userId || !this.allowedUserIds.includes(userId)) {
        return;
      }

      await ctx.reply('👋 Welcome! I am your AI assistant. How can I help you today?');
    });

    bot.command('help', async (ctx) => {
      const userId = ctx.from?.id;

      // Check if user is allowed
      if (!userId || !this.allowedUserIds.includes(userId)) {
        return;
      }

      await ctx.reply(
        'Available commands:\n' +
          '/start - Start a conversation\n' +
          '/help - Show this help message\n' +
          '/clear - Clear conversation history',
      );
    });

    bot.command('clear', async (ctx) => {
      const userId = ctx.from?.id;

      // Check if user is allowed
      if (!userId || !this.allowedUserIds.includes(userId)) {
        return;
      }

      // In a full implementation, we would clear the conversation history here
      await ctx.reply('Conversation history cleared.');
    });

    // Start the bot
    await this.telegramService.startBot();
  }

  async onModuleDestroy(): Promise<void> {
    this.telegramService.stopBot();
  }
}
