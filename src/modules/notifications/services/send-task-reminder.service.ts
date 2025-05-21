import { Injectable, Logger } from '@nestjs/common';
import { Task } from '../domain/models/task.model';
import { NotificationService } from '../infrastructure/services/notification.service';

@Injectable()
export class SendTaskReminderService {
  private readonly logger = new Logger(SendTaskReminderService.name);

  constructor(private readonly notificationService: NotificationService) {}

  async sendTaskReminder(task: Task, minutesBefore: number, userId?: number): Promise<boolean> {
    this.logger.log(
      `Sending reminder for task "${task.getTitle()}" ${minutesBefore} minutes before`,
    );

    try {
      return await this.notificationService.sendTaskReminder(task, minutesBefore);
    } catch (error) {
      this.logger.error(`Failed to send task reminder: ${error.message}`, error.stack);
      return false;
    }
  }
}
