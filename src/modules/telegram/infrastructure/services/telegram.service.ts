import { Injectable } from '@nestjs/common';
import { ITelegramService } from '../../domain/interfaces/telegram-service.interface';
import { ConfigService } from '../../../../shared/infrastructure/config/config.service';
import { Telegraf, Context } from 'telegraf';

type ParseMode = 'Markdown' | 'MarkdownV2' | 'HTML';

@Injectable()
export class TelegramService implements ITelegramService {
  private bot: Telegraf;
  private currentUpdate: any;
  private currentContext: any;

  constructor(private readonly configService: ConfigService) {
    const token = this.configService.getTelegramBotToken();

    if (!token) {
      throw new Error('Telegram bot token is not configured');
    }

    this.bot = new Telegraf(token);
  }

  setCurrentContext(update: any, context: any): void {
    this.currentUpdate = update;
    this.currentContext = context;
  }

  async sendMessage(
    chatId: number,
    text: string,
    parseMode: string = 'Markdown',
  ): Promise<boolean> {
    try {
      // Sanitize markdown if needed
      const sanitizedText = parseMode === 'Markdown' ? this.sanitizeMarkdown(text) : text;

      await this.bot.telegram.sendMessage(chatId, sanitizedText, {
        parse_mode: parseMode as ParseMode,
      });
      return true;
    } catch (error) {
      console.error(`Error sending message to chat ${chatId}:`, error);

      // Fallback to plain text if markdown parsing fails
      if (parseMode !== 'None') {
        try {
          await this.bot.telegram.sendMessage(chatId, text, {
            parse_mode: undefined,
          });
          return true;
        } catch (fallbackError) {
          console.error(`Fallback error sending plain text to chat ${chatId}:`, fallbackError);
        }
      }

      return false;
    }
  }

  async sendMessageToUser(
    userId: number,
    text: string,
    parseMode: string = 'Markdown',
  ): Promise<boolean> {
    try {
      // Sanitize markdown if needed
      const sanitizedText = parseMode === 'Markdown' ? this.sanitizeMarkdown(text) : text;

      await this.bot.telegram.sendMessage(userId, sanitizedText, {
        parse_mode: parseMode as ParseMode,
      });
      return true;
    } catch (error) {
      console.error(`Error sending message to user ${userId}:`, error);

      // Fallback to plain text if markdown parsing fails
      if (parseMode !== 'None') {
        try {
          await this.bot.telegram.sendMessage(userId, text, {
            parse_mode: undefined,
          });
          return true;
        } catch (fallbackError) {
          console.error(`Fallback error sending plain text to user ${userId}:`, fallbackError);
        }
      }

      return false;
    }
  }

  async replyToCurrentMessage(text: string, parseMode: string = 'Markdown'): Promise<boolean> {
    if (!this.currentUpdate || !this.currentContext) {
      console.error('Cannot reply: no current context set');
      return false;
    }

    try {
      const chatId = this.currentUpdate.message?.chat?.id;
      const messageId = this.currentUpdate.message?.message_id;

      if (!chatId) {
        console.error('Cannot reply: no chat ID in current update');
        return false;
      }

      // Sanitize markdown if needed
      const sanitizedText = parseMode === 'Markdown' ? this.sanitizeMarkdown(text) : text;

      await this.bot.telegram.sendMessage(chatId, sanitizedText, {
        parse_mode: parseMode as ParseMode,
        reply_to_message_id: messageId as number,
      } as any);
      return true;
    } catch (error) {
      console.error('Error replying to current message:', error);

      // Fallback to plain text if markdown parsing fails
      if (parseMode !== 'None') {
        try {
          const chatId = this.currentUpdate.message?.chat?.id;
          const messageId = this.currentUpdate.message?.message_id;

          await this.bot.telegram.sendMessage(chatId, text, {
            parse_mode: undefined,
            reply_to_message_id: messageId as number,
          } as any);
          return true;
        } catch (fallbackError) {
          console.error('Fallback error replying with plain text:', fallbackError);
        }
      }

      return false;
    }
  }

  // Helper method to sanitize markdown and avoid parsing errors
  private sanitizeMarkdown(text: string): string {
    if (!text) return '';

    // Fix common markdown issues
    let sanitized = text;

    // Fix unclosed asterisks
    const asteriskCount = (sanitized.match(/\*/g) || []).length;
    if (asteriskCount % 2 !== 0) {
      sanitized = sanitized.replace(/\*([^*]*)$/g, '*$1');
    }

    // Fix unclosed underscores
    const underscoreCount = (sanitized.match(/_/g) || []).length;
    if (underscoreCount % 2 !== 0) {
      sanitized = sanitized.replace(/_([^_]*)$/g, '_$1');
    }

    // Fix unclosed backticks
    const backtickCount = (sanitized.match(/`/g) || []).length;
    if (backtickCount % 2 !== 0) {
      sanitized = sanitized.replace(/`([^`]*)$/g, '`$1');
    }

    // Fix lists with asterisks that might be confused with bold/italic markers
    sanitized = sanitized.replace(/^\s*\*\s+/gm, '• ');

    return sanitized;
  }

  // Additional methods for the Telegram bot
  async startBot(): Promise<void> {
    await this.bot.launch();
    console.log('Telegram bot started');
  }

  stopBot(): void {
    this.bot.stop();
    console.log('Telegram bot stopped');
  }

  getBot(): Telegraf<Context> {
    return this.bot;
  }
}
