import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ScheduleModule } from '@nestjs/schedule';

import { SharedModule } from './shared/shared.module';
import { TelegramModule } from './modules/telegram/telegram.module';
import { LlmModule } from './modules/llm/llm.module';
import { VaultModule } from './modules/vault/vault.module';
import { ToolsModule } from './modules/tools/tools.module';
import { NotificationsModule } from './modules/notifications/notifications.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
    }),
    ScheduleModule.forRoot(),
    NotificationsModule,
    SharedModule,
    TelegramModule,
    LlmModule,
    VaultModule,
    ToolsModule,
  ],
})
export class AppModule {}
