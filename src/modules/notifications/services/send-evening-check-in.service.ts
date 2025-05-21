import { Injectable, Logger } from '@nestjs/common';
import { NotificationService } from '../infrastructure/services/notification.service';

@Injectable()
export class SendEveningCheckInService {
  private readonly logger = new Logger(SendEveningCheckInService.name);

  constructor(private readonly notificationService: NotificationService) {}

  async sendEveningCheckIn(userId: number): Promise<boolean> {
    this.logger.log(`Sending evening check-in to user ${userId}`);

    try {
      return await this.notificationService.sendEveningCheckIn(userId);
    } catch (error) {
      this.logger.error(`Failed to send evening check-in: ${error.message}`, error.stack);
      return false;
    }
  }
}
