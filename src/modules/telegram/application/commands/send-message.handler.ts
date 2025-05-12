import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { SendMessageCommand } from './send-message.command';
import { Inject } from '@nestjs/common';
import { ITelegramService } from '../../domain/interfaces/telegram-service.interface';
import { Message } from '../../domain/entities/message.entity';
import { v4 as uuidv4 } from 'uuid';

@CommandHandler(SendMessageCommand)
export class SendMessageHandler implements ICommandHandler<SendMessageCommand> {
  constructor(@Inject('ITelegramService') private readonly telegramService: ITelegramService) {}

  async execute(command: SendMessageCommand): Promise<void> {
    const { chatId, text, parseMode } = command;

    // Create a message entity
    const message = new Message(
      uuidv4(),
      chatId,
      0, // System message (not from a specific user)
      text,
    );

    // Send the message
    const success = await this.telegramService.sendMessage(chatId, text, parseMode);

    if (success) {
      message.markAsSent();
    }
  }
}
