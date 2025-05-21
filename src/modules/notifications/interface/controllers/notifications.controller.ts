import { Controller, Post, Body, Param, Get, Inject, HttpStatus, HttpCode } from '@nestjs/common';
import { SendTaskReminderService } from '../../services/send-task-reminder.service';
import { SendMorningDigestService } from '../../services/send-morning-digest.service';
import { SendEveningCheckInService } from '../../services/send-evening-check-in.service';
import { ITaskAnalyzerService } from '../../domain/interfaces/task-analyzer-service.interface';
import { INotificationService } from '../../domain/interfaces/notification-service.interface';
import { Task } from '../../domain/models/task.model';
import { ConfigService } from '../../../../shared/infrastructure/config/config.service';
import { Logger } from '@nestjs/common';
import { NotificationService } from '../../infrastructure/services/notification.service';
import { TaskAnalyzerService } from '../../infrastructure/services/task-analyzer.service';

@Controller('notifications')
export class NotificationsController {
  private readonly logger = new Logger(NotificationsController.name);

  constructor(
    private readonly sendTaskReminderService: SendTaskReminderService,
    private readonly sendMorningDigestService: SendMorningDigestService,
    private readonly sendEveningCheckInService: SendEveningCheckInService,
    private readonly taskAnalyzer: TaskAnalyzerService,
    private readonly notificationService: NotificationService,
    private readonly configService: ConfigService,
  ) {}

  @Post('task-reminder/:userId')
  async sendTaskReminder(@Param('userId') userId: string, @Body() taskData: any): Promise<boolean> {
    const task = new Task(taskData.id, taskData);
    return this.sendTaskReminderService.sendTaskReminder(
      task,
      taskData.minutesBefore || 15,
      parseInt(userId, 10),
    );
  }

  @Post('morning-digest/:userId')
  async sendMorningDigest(@Param('userId') userId: string): Promise<boolean> {
    return this.sendMorningDigestService.sendMorningDigest(parseInt(userId, 10));
  }

  @Post('evening-check-in/:userId')
  async sendEveningCheckIn(@Param('userId') userId: string): Promise<boolean> {
    return this.sendEveningCheckInService.sendEveningCheckIn(parseInt(userId, 10));
  }

  @Post('reset-reminders')
  async resetReminders(): Promise<{ success: boolean; message: string }> {
    try {
      await this.notificationService.resetAndRescheduleAllReminders();
      return {
        success: true,
        message: 'All reminders have been reset and rescheduled successfully',
      };
    } catch (error) {
      return {
        success: false,
        message: `Failed to reset reminders: ${error.message}`,
      };
    }
  }

  @Post('broadcast-morning-digest')
  @HttpCode(HttpStatus.OK)
  async broadcastMorningDigest(): Promise<{ success: boolean; message: string }> {
    try {
      this.logger.log('Broadcasting morning digest to all users');
      const userIds = this.configService.getTelegramUserIds();
      const results = [];

      for (const userId of userIds) {
        try {
          const numericUserId = parseInt(userId, 10);
          if (!isNaN(numericUserId)) {
            const result = await this.notificationService.sendMorningDigest(numericUserId);
            results.push({ userId: numericUserId, success: result });
          }
        } catch (error) {
          this.logger.error(`Error sending morning digest to user ${userId}:`, error);
          results.push({ userId, success: false, error: error.message });
        }
      }

      const successCount = results.filter((r) => r.success).length;
      return {
        success: successCount > 0,
        message: `Morning digest sent to ${successCount}/${userIds.length} users`,
      };
    } catch (error) {
      this.logger.error(`Error broadcasting morning digest:`, error);
      return {
        success: false,
        message: `Failed to broadcast morning digest: ${error.message}`,
      };
    }
  }

  @Post('broadcast-evening-check-in')
  @HttpCode(HttpStatus.OK)
  async broadcastEveningCheckIn(): Promise<{ success: boolean; message: string }> {
    try {
      this.logger.log('Broadcasting evening check-in to all users');
      const userIds = this.configService.getTelegramUserIds();
      const results = [];

      for (const userId of userIds) {
        try {
          const numericUserId = parseInt(userId, 10);
          if (!isNaN(numericUserId)) {
            const result = await this.notificationService.sendEveningCheckIn(numericUserId);
            results.push({ userId: numericUserId, success: result });
          }
        } catch (error) {
          this.logger.error(`Error sending evening check-in to user ${userId}:`, error);
          results.push({ userId, success: false, error: error.message });
        }
      }

      const successCount = results.filter((r) => r.success).length;
      return {
        success: successCount > 0,
        message: `Evening check-in sent to ${successCount}/${userIds.length} users`,
      };
    } catch (error) {
      this.logger.error(`Error broadcasting evening check-in:`, error);
      return {
        success: false,
        message: `Failed to broadcast evening check-in: ${error.message}`,
      };
    }
  }

  @Get('tasks/today')
  async getTodaysTasks(): Promise<Task[]> {
    return this.taskAnalyzer.getTodaysTasks();
  }

  @Get('tasks/overdue')
  async getOverdueTasks(): Promise<Task[]> {
    return this.taskAnalyzer.getOverdueTasks();
  }

  @Get('tasks/completed-today')
  async getCompletedTasksToday(): Promise<Task[]> {
    return this.taskAnalyzer.getCompletedTasksToday();
  }

  @Get('tasks/postponed')
  async getPostponedTasks(): Promise<Task[]> {
    return this.taskAnalyzer.getPostponedTasks();
  }
}
