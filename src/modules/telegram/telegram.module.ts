import { Module } from '@nestjs/common';
import { CqrsModule } from '@nestjs/cqrs';
import { TelegramService } from './infrastructure/services/telegram.service';
import { TelegramAppService } from './application/services/telegram-app.service';
import { CommandHandlers } from './application/commands';
import { LlmModule } from '../llm/llm.module';
import { VaultModule } from '../vault/vault.module';

@Module({
  imports: [CqrsModule, LlmModule, VaultModule],
  providers: [
    TelegramService,
    TelegramAppService,
    ...CommandHandlers,
    {
      provide: 'ITelegramService',
      useExisting: TelegramService,
    },
  ],
  exports: ['ITelegramService', TelegramService, TelegramAppService],
})
export class TelegramModule {}
