import { Module } from '@nestjs/common';
import { SchedulingService } from './infrastructure/services/scheduling.service';
import { RecurringEventsService } from './infrastructure/services/recurring-events.service';
import { VaultModule } from '../vault/vault.module';
import { TelegramModule } from '../telegram/telegram.module';

@Module({
  imports: [VaultModule, TelegramModule],
  providers: [
    SchedulingService,
    RecurringEventsService,
    {
      provide: 'ISchedulingService',
      useExisting: SchedulingService,
    },
    {
      provide: 'IRecurringEventsEngine',
      useExisting: RecurringEventsService,
    },
  ],
  exports: ['ISchedulingService', 'IRecurringEventsEngine', RecurringEventsService],
})
export class RecurringEventsModule {}
