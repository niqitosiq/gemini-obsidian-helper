import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { Inject, Logger } from '@nestjs/common';
import { SendTaskReminderCommand } from './send-task-reminder.command';
import { INotificationService } from '../../domain/interfaces/notification-service.interface';
import { NotificationService } from '../../infrastructure/services/notification.service';

@CommandHandler(SendTaskReminderCommand)
export class SendTaskReminderHandler implements ICommandHandler<SendTaskReminderCommand> {
  private readonly logger = new Logger(SendTaskReminderHandler.name);

  constructor(private readonly notificationService: NotificationService) {}

  async execute(command: SendTaskReminderCommand): Promise<boolean> {
    const { task, minutesBefore } = command;

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
