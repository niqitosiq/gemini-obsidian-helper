import { Injectable, Logger } from '@nestjs/common';
import { NotificationService } from '../infrastructure/services/notification.service';

@Injectable()
export class SendMorningDigestService {
  private readonly logger = new Logger(SendMorningDigestService.name);

  constructor(private readonly notificationService: NotificationService) {}

  async sendMorningDigest(userId: number): Promise<boolean> {
    this.logger.log(`Sending morning digest to user ${userId}`);

    try {
      return await this.notificationService.sendMorningDigest(userId);
    } catch (error) {
      this.logger.error(`Failed to send morning digest: ${error.message}`, error.stack);
      return false;
    }
  }
}
