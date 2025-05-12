import { Module, forwardRef } from '@nestjs/common';
import { CqrsModule } from '@nestjs/cqrs';
import {
  CreateFileToolHandler,
  ModifyFileToolHandler,
  DeleteFileToolHandler,
  ReplyToolHandler,
  FinishToolHandler,
} from './infrastructure/services/file-tools.service';
import { FilePathService } from './infrastructure/services/file-path.service';
import { VaultModule } from '../vault/vault.module';
import { ToolsRegistryService } from './application/services/tools-registry.service';
import { TelegramModule } from '../telegram/telegram.module';
import { ConfigModule } from '@nestjs/config';
import { SharedModule } from '../../shared/shared.module';
// import { SendMessageHandler } from '../telegram/application/commands/send-message.handler';
import { DiscoveryModule } from '@nestjs/core';

@Module({
  imports: [SharedModule, VaultModule, DiscoveryModule, CqrsModule],
  providers: [
    FilePathService,
    CreateFileToolHandler,
    ModifyFileToolHandler,
    DeleteFileToolHandler,
    ReplyToolHandler,
    FinishToolHandler,
    ToolsRegistryService,
  ],
  exports: [
    FilePathService,
    ToolsRegistryService,
    CreateFileToolHandler,
    ModifyFileToolHandler,
    DeleteFileToolHandler,
    ReplyToolHandler,
    FinishToolHandler,
  ],
})
export class ToolsModule {}
