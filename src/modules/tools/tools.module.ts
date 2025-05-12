import { Module } from '@nestjs/common';
import {
  CreateFileToolHandler,
  ModifyFileToolHandler,
  DeleteFileToolHandler,
} from './infrastructure/services/file-tools.service';
import { VaultModule } from '../vault/vault.module';
import { ToolsRegistryService } from './application/services/tools-registry.service';

@Module({
  imports: [VaultModule],
  providers: [
    CreateFileToolHandler,
    ModifyFileToolHandler,
    DeleteFileToolHandler,
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
  ],
  exports: [
    'CreateFileTool',
    'ModifyFileTool',
    'DeleteFileTool',
    ToolsRegistryService,
    CreateFileToolHandler,
    ModifyFileToolHandler,
    DeleteFileToolHandler,
  ],
})
export class ToolsModule {}
