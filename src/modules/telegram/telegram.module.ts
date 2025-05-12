import { Module, forwardRef } from '@nestjs/common';
import { TelegramService } from './infrastructure/services/telegram.service';
import { TelegramAppService } from './application/services/telegram-app.service';
import { ProcessMessageHandler } from './application/commands/process-message.handler';
import { LlmModule } from '../llm/llm.module';
import { VaultModule } from '../vault/vault.module';
import { ToolsModule } from '../tools/tools.module';
import { NotificationsModule } from '../notifications/notifications.module';
import { SharedModule } from '../../shared/shared.module';
import { SendMessageHandler } from './application/commands/send-message.handler';
import { CommandBus, CqrsModule } from '@nestjs/cqrs';

@Module({
  imports: [
    SharedModule,
    CqrsModule,
    forwardRef(() => LlmModule),
    VaultModule,
    forwardRef(() => ToolsModule),
    forwardRef(() => NotificationsModule),
  ],
  providers: [TelegramService, TelegramAppService, SendMessageHandler, ProcessMessageHandler],
  exports: [TelegramService, TelegramAppService],
})
export class TelegramModule {}
