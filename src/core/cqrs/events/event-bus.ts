import { Injectable } from '@nestjs/common';
import { EventBus as NestEventBus } from '@nestjs/cqrs';
import { IEvent } from './event.interface';

@Injectable()
export class EventBus {
  constructor(private readonly nestEventBus: NestEventBus) {}

  publish<T extends IEvent>(event: T): void {
    this.nestEventBus.publish(event);
  }
}
