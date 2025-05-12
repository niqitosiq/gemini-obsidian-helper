import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { Inject, Logger } from '@nestjs/common';
import { SendEveningCheckInCommand } from './send-evening-check-in.command';
import { INotificationService } from '../../domain/interfaces/notification-service.interface';
import { NotificationService } from '../../infrastructure/services/notification.service';

@CommandHandler(SendEveningCheckInCommand)
export class SendEveningCheckInHandler implements ICommandHandler<SendEveningCheckInCommand> {
  private readonly logger = new Logger(SendEveningCheckInHandler.name);

  constructor(private readonly notificationService: NotificationService) {}

  async execute(command: SendEveningCheckInCommand): Promise<boolean> {
    const { userId } = command;

    this.logger.log(`Sending evening check-in to user ${userId}`);

    try {
      return await this.notificationService.sendEveningCheckIn(userId);
    } catch (error) {
      this.logger.error(`Failed to send evening check-in: ${error.message}`, error.stack);
      return false;
    }
  }
}
