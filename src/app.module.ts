import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { CqrsModule } from '@nestjs/cqrs';
import { ScheduleModule } from '@nestjs/schedule';

import { RecurringEventsModule } from './modules/recurring-events/recurring-events.module';
import { SharedModule } from './shared/shared.module';
import { TelegramModule } from './modules/telegram/telegram.module';
import { LlmModule } from './modules/llm/llm.module';
import { VaultModule } from './modules/vault/vault.module';
import { ToolsModule } from './modules/tools/tools.module';
import { CommandHandlers } from './modules/telegram/application/commands';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
    }),
    CqrsModule,
    ScheduleModule.forRoot(),
    SharedModule,
    TelegramModule,
    LlmModule,
    VaultModule,
    RecurringEventsModule,
    ToolsModule,
  ],
  providers: [...CommandHandlers],
})
export class AppModule {}
