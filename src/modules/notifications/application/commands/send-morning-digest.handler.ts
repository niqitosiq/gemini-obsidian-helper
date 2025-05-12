import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { Inject, Logger } from '@nestjs/common';
import { SendMorningDigestCommand } from './send-morning-digest.command';
import { INotificationService } from '../../domain/interfaces/notification-service.interface';
import { NotificationService } from '../../infrastructure/services/notification.service';

@CommandHandler(SendMorningDigestCommand)
export class SendMorningDigestHandler implements ICommandHandler<SendMorningDigestCommand> {
  private readonly logger = new Logger(SendMorningDigestHandler.name);

  constructor(private readonly notificationService: NotificationService) {}

  async execute(command: SendMorningDigestCommand): Promise<boolean> {
    const { userId } = command;

    this.logger.log(`Sending morning digest to user ${userId}`);

    try {
      return await this.notificationService.sendMorningDigest(userId);
    } catch (error) {
      this.logger.error(`Failed to send morning digest: ${error.message}`, error.stack);
      return false;
    }
  }
}
