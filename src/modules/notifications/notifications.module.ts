import { Module } from '@nestjs/common';
import { CqrsModule } from '@nestjs/cqrs';
import { ScheduleModule } from '@nestjs/schedule';
import { VaultModule } from '../vault/vault.module';
import { SharedModule } from '../../shared/shared.module';
import { LlmModule } from '../llm/llm.module';

// Command Handlers
import { SendTaskReminderHandler } from './application/commands/send-task-reminder.handler';
import { SendMorningDigestHandler } from './application/commands/send-morning-digest.handler';
import { SendEveningCheckInHandler } from './application/commands/send-evening-check-in.handler';

// Services
import { NotificationService } from './infrastructure/services/notification.service';
import { TaskAnalyzerService } from './infrastructure/services/task-analyzer.service';
import { SchedulingService } from './infrastructure/services/scheduling.service';

// Controllers
import { NotificationsController } from './interface/controllers/notifications.controller';

const commandHandlers = [];

const services = [];

@Module({
  imports: [VaultModule, SharedModule, LlmModule],
  providers: [
    SendTaskReminderHandler,
    SendMorningDigestHandler,
    SendEveningCheckInHandler,
    NotificationService,
    TaskAnalyzerService,
    SchedulingService,
  ],
  controllers: [NotificationsController],
  exports: [NotificationService, TaskAnalyzerService, SchedulingService, NotificationService],
})
export class NotificationsModule {}
