import { DomainEvent } from '../../../../core/ddd/domain-event';
import { IEvent } from '../../../../core/cqrs/events/event.interface';

export class MessageSentEvent extends DomainEvent implements IEvent {
  readonly _eventBrand: symbol = Symbol('MessageSentEvent');

  constructor(
    public readonly messageId: string,
    public readonly chatId: number,
    public readonly userId: number,
  ) {
    super();
  }
}
