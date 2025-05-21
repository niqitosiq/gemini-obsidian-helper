import { Injectable, Logger } from '@nestjs/common';
import { TelegramService } from '../../infrastructure/services/telegram.service';

@Injectable()
export class SendMessageService {
  private readonly logger = new Logger(SendMessageService.name);

  constructor(private readonly telegramService: TelegramService) {}

  async sendMessage(userId: number, message: string, parseMode?: string): Promise<boolean> {
    this.logger.log(`Sending message to user ${userId}`);

    try {
      return await this.telegramService.sendMessageToUser(userId, message, parseMode);
    } catch (error) {
      this.logger.error(`Failed to send message: ${error.message}`, error.stack);
      return false;
    }
  }
}
