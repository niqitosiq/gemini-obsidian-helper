import { Module, forwardRef } from '@nestjs/common';
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

@Module({
  imports: [ConfigModule, VaultModule, forwardRef(() => TelegramModule)],
  providers: [
    FilePathService,
    CreateFileToolHandler,
    ModifyFileToolHandler,
    DeleteFileToolHandler,
    ReplyToolHandler,
    FinishToolHandler,
    ToolsRegistryService,
    {
      provide: 'CreateFileTool',
      useExisting: CreateFileToolHandler,
    },
    {
      provide: 'ModifyFileTool',
      useExisting: ModifyFileToolHandler,
    },
    {
      provide: 'DeleteFileTool',
      useExisting: DeleteFileToolHandler,
    },
    {
      provide: 'ReplyTool',
      useExisting: ReplyToolHandler,
    },
    {
      provide: 'FinishTool',
      useExisting: FinishToolHandler,
    },
  ],
  exports: [
    FilePathService,
    'CreateFileTool',
    'ModifyFileTool',
    'DeleteFileTool',
    'ReplyTool',
    'FinishTool',
    ToolsRegistryService,
    CreateFileToolHandler,
    ModifyFileToolHandler,
    DeleteFileToolHandler,
    ReplyToolHandler,
    FinishToolHandler,
  ],
})
export class ToolsModule {}
