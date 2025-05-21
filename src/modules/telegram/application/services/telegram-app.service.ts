import { Injectable, OnModuleInit, OnModuleDestroy, Inject, forwardRef } from '@nestjs/common';
import { TelegramService } from '../../infrastructure/services/telegram.service';
import { MessageDto } from '../../interface/dtos/message.dto';
import { ConfigService } from '../../../../shared/infrastructure/config/config.service';
import { ProcessMessageService } from '../services/process-message.service';
import { ModuleRef } from '@nestjs/core';
import { Logger } from '@nestjs/common';
import { INotificationService } from '../../../notifications/domain/interfaces/notification-service.interface';
import { NotificationService } from 'src/modules/notifications/infrastructure/services/notification.service';
import { GeminiService } from '../../../llm/infrastructure/services/gemini.service';
import * as path from 'path';
import * as fs from 'fs';

@Injectable()
export class TelegramAppService implements OnModuleInit, OnModuleDestroy {
  private allowedUserIds: number[] = [];
  private readonly logger = new Logger(TelegramAppService.name);

  constructor(
    private readonly telegramService: TelegramService,
    private readonly configService: ConfigService,
    private readonly processMessageService: ProcessMessageService,
    private readonly moduleRef: ModuleRef,
    @Inject(forwardRef(() => NotificationService))
    private readonly notificationService: NotificationService,
    private readonly geminiService: GeminiService,
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
          // Use the service directly
          await this.processMessageService.processMessage(messageDto);
        } catch (error) {
          console.error('Error processing message:', error);
          await ctx.reply('Sorry, there was an error processing your message.');
        }
      }

      // Process voice messages
      else if (ctx.message && 'voice' in ctx.message && ctx.message.voice) {
        try {
          const fileId = ctx.message.voice.file_id;
          const chatId = ctx.chat.id;
          const userId = ctx.from?.id;
          // Use a temp file path
          const tempDir = path.join(process.cwd(), 'temp');
          if (!fs.existsSync(tempDir)) {
            fs.mkdirSync(tempDir);
          }
          const tempFilePath = path.join(tempDir, `${fileId}.ogg`);
          await ctx.reply('⏳ Downloading and transcribing your voice message...');
          await this.telegramService.downloadFile(fileId, tempFilePath);
          // Transcribe using Gemini
          let transcription: string | null = null;
          try {
            transcription = await this.geminiService.transcribeAudioAsync(tempFilePath);
          } catch (err) {
            this.logger.error('Error during Gemini transcription:', err);
          }
          // Clean up temp file
          try {
            fs.unlinkSync(tempFilePath);
          } catch {}
          if (
            transcription &&
            typeof transcription === 'string' &&
            transcription !== 'Audio transcription is not implemented in this adapter'
          ) {
            // Pass transcription to processMessageService as if it were a text message
            const messageDto = new MessageDto(chatId, userId, transcription);
            await this.processMessageService.processMessage(messageDto);
          } else {
            await ctx.reply('❌ Sorry, could not transcribe the audio.');
          }
        } catch (error) {
          this.logger.error('Error handling voice message:', error);
          await ctx.reply('❌ Error processing your voice message.');
        }
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
          '/clear - Clear conversation history\n' +
          '/reset_notifications - Reset all notifications\n' +
          '/morning_digest - Send morning digest\n' +
          '/evening_check - Send evening check-in',
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

    // Add a command to reset notifications
    bot.command('reset_notifications', async (ctx) => {
      const userId = ctx.from?.id;

      // Check if user is allowed
      if (!userId || !this.allowedUserIds.includes(userId)) {
        return;
      }

      try {
        await ctx.reply('🔄 Resetting all notifications...');

        try {
          // Use the injected notification service
          await this.notificationService.resetAndRescheduleAllReminders();
          await ctx.reply('✅ All notifications have been reset and rescheduled successfully.');
        } catch (error) {
          this.logger.error('Error resetting notifications:', error);
          await ctx.reply(`❌ Failed to reset notifications: ${error.message || 'Unknown error'}`);
        }
      } catch (error) {
        this.logger.error('Error handling reset_notifications command:', error);
        await ctx.reply(`❌ An unexpected error occurred: ${error.message || 'Unknown error'}`);
      }
    });

    // Add command for morning digest
    bot.command('morning_digest', async (ctx) => {
      const userId = ctx.from?.id;

      // Check if user is allowed
      if (!userId || !this.allowedUserIds.includes(userId)) {
        return;
      }

      try {
        await ctx.reply('📋 Generating your morning digest...');
        const result = await this.notificationService.sendMorningDigest(userId);

        if (!result) {
          await ctx.reply('❌ Failed to generate morning digest. Please try again later.');
        }
      } catch (error) {
        this.logger.error('Error sending morning digest:', error);
        await ctx.reply(`❌ Error: ${error.message || 'Unknown error'}`);
      }
    });

    // Add command for evening check-in
    bot.command('evening_check', async (ctx) => {
      const userId = ctx.from?.id;

      // Check if user is allowed
      if (!userId || !this.allowedUserIds.includes(userId)) {
        return;
      }

      try {
        await ctx.reply('📝 Generating your evening check-in...');
        const result = await this.notificationService.sendEveningCheckIn(userId);

        if (!result) {
          await ctx.reply('❌ Failed to generate evening check-in. Please try again later.');
        }
      } catch (error) {
        this.logger.error('Error sending evening check-in:', error);
        await ctx.reply(`❌ Error: ${error.message || 'Unknown error'}`);
      }
    });

    // Start the bot
    await this.telegramService.startBot();
  }

  async onModuleDestroy(): Promise<void> {
    this.telegramService.stopBot();
  }
}
