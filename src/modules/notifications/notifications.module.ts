import { Module, forwardRef } from '@nestjs/common';
import { ScheduleModule } from '@nestjs/schedule';
import { VaultModule } from '../vault/vault.module';
import { SharedModule } from '../../shared/shared.module';
import { LlmModule } from '../llm/llm.module';
import { TelegramModule } from '../telegram/telegram.module';

// Services
import { SendTaskReminderService } from './services/send-task-reminder.service';
import { SendMorningDigestService } from './services/send-morning-digest.service';
import { SendEveningCheckInService } from './services/send-evening-check-in.service';
import { NotificationService } from './infrastructure/services/notification.service';
import { TaskAnalyzerService } from './infrastructure/services/task-analyzer.service';
import { SchedulingService } from './infrastructure/services/scheduling.service';

// Controllers
import { NotificationsController } from './interface/controllers/notifications.controller';

@Module({
  imports: [VaultModule, SharedModule, LlmModule, forwardRef(() => TelegramModule)],
  providers: [
    SendTaskReminderService,
    SendMorningDigestService,
    SendEveningCheckInService,
    NotificationService,
    TaskAnalyzerService,
    SchedulingService,
  ],
  controllers: [NotificationsController],
  exports: [
    NotificationService,
    TaskAnalyzerService,
    SchedulingService,
    SendTaskReminderService,
    SendMorningDigestService,
    SendEveningCheckInService,
  ],
})
export class NotificationsModule {}
