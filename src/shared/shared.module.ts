import { Module, Global } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ConfigService } from './infrastructure/config/config.service';
import { HistoryService } from './infrastructure/persistence/history.service';
import { PromptBuilderService } from './infrastructure/services/prompt-builder.service';

@Global()
@Module({
  imports: [ConfigModule],
  providers: [ConfigService, HistoryService, PromptBuilderService],
  exports: [ConfigService, HistoryService, PromptBuilderService],
})
export class SharedModule {}
