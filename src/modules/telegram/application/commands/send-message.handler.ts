import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { Inject, Logger } from '@nestjs/common';
import { SendMessageCommand } from './send-message.command';
import { ITelegramService } from '../../domain/interfaces/telegram-service.interface';
import { TelegramService } from '../../infrastructure/services/telegram.service';

@CommandHandler(SendMessageCommand)
export class SendMessageHandler implements ICommandHandler<SendMessageCommand> {
  private readonly logger = new Logger(SendMessageHandler.name);

  // private readonly telegramService: TelegramService
  constructor() {
    // this.telegramService = telegramService;
    console.log('SendMessageHandler constructor CALLED');
    console.log(
      `SendMessageHandler handles command: ${SendMessageCommand.name}, Type: ${typeof SendMessageCommand}`,
    );
  }

  async execute(command: SendMessageCommand): Promise<boolean> {
    const { userId, message, parseMode } = command;

    this.logger.log(`Sending message to user ${userId}`);

    // try {
    //   // return await this.telegramService.sendMessageToUser(userId, message, parseMode);
    //   return true;
    // } catch (error) {
    //   this.logger.error(`Failed to send message: ${error.message}`, error.stack);
    //   return false;
    // }
    console.log('SendMessageHandler execute');
    return true;
  }
}
