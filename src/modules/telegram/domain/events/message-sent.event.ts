import { DomainEvent } from '../../../../core/ddd/domain-event';

export class MessageSentEvent extends DomainEvent {
  constructor(
    public readonly messageId: string,
    public readonly chatId: number,
    public readonly userId: number,
  ) {
    super();
  }
}
