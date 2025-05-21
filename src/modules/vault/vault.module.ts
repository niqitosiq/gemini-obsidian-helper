import { Module } from '@nestjs/common';
import { VaultService } from './infrastructure/services/vault.service';

@Module({
  providers: [
    VaultService,
    {
      provide: 'IVaultService',
      useExisting: VaultService,
    },
  ],
  exports: ['IVaultService', VaultService],
})
export class VaultModule {}
