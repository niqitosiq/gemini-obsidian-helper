import { Module, forwardRef } from '@nestjs/common';
import { TelegramService } from './infrastructure/services/telegram.service';
import { TelegramAppService } from './application/services/telegram-app.service';
import { ProcessMessageService } from './application/services/process-message.service';
import { LlmModule } from '../llm/llm.module';
import { VaultModule } from '../vault/vault.module';
import { ToolsModule } from '../tools/tools.module';
import { NotificationsModule } from '../notifications/notifications.module';
import { SharedModule } from '../../shared/shared.module';
import { SendMessageService } from './application/services/send-message.service';

@Module({
  imports: [
    SharedModule,
    forwardRef(() => LlmModule),
    VaultModule,
    forwardRef(() => ToolsModule),
    forwardRef(() => NotificationsModule),
  ],
  providers: [TelegramService, TelegramAppService, SendMessageService, ProcessMessageService],
  exports: [TelegramService, TelegramAppService, SendMessageService],
})
export class TelegramModule {}
