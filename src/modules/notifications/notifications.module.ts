import { Module, forwardRef } from '@nestjs/common';
import { ScheduleModule } from '@nestjs/schedule';
import { VaultModule } from '../vault/vault.module';
import { SharedModule } from '../../shared/shared.module';
import { LlmModule } from '../llm/llm.module';
import { TelegramModule } from '../telegram/telegram.module';
import { VaultService } from '../vault/infrastructure/services/vault.service';

// Services
import { SendTaskReminderService } from './services/send-task-reminder.service';
import { SendMorningDigestService } from './services/send-morning-digest.service';
import { SendEveningCheckInService } from './services/send-evening-check-in.service';
import { NotificationService } from './infrastructure/services/notification.service';
import { TaskAnalyzerService } from './infrastructure/services/task-analyzer.service';
import { SchedulingService } from './infrastructure/services/scheduling.service';

// Controllers
import { NotificationsController } from './interface/controllers/notifications.controller';
import { ProcessMessageService } from '../telegram/application/services/process-message.service';
import { ToolsRegistryService } from '../tools/application/services/tools-registry.service';
import { CreateFileToolHandler } from '../tools/infrastructure/services/file-tools.service';
import { ModifyFileToolHandler } from '../tools/infrastructure/services/file-tools.service';
import { DeleteFileToolHandler } from '../tools/infrastructure/services/file-tools.service';
import { ReplyToolHandler } from '../tools/infrastructure/services/file-tools.service';
import { FinishToolHandler } from '../tools/infrastructure/services/file-tools.service';
import { FilePathService } from '../tools/infrastructure/services/file-path.service';
@Module({
  imports: [VaultModule, SharedModule, LlmModule, forwardRef(() => TelegramModule)],
  providers: [
    SendTaskReminderService,
    SendMorningDigestService,
    SendEveningCheckInService,
    NotificationService,
    TaskAnalyzerService,
    SchedulingService,
    VaultService,
    ProcessMessageService,
    ToolsRegistryService,
    CreateFileToolHandler,
    ModifyFileToolHandler,
    DeleteFileToolHandler,
    ReplyToolHandler,
    FinishToolHandler,
    FilePathService,
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
