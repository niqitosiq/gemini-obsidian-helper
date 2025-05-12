import { AggregateRoot } from '../../../../core/ddd/aggregate-root';
import { MessageSentEvent } from '../events/message-sent.event';

export class Message extends AggregateRoot<string> {
  private readonly chatId: number;
  private readonly userId: number;
  private readonly text: string;
  private readonly timestamp: Date;

  constructor(id: string, chatId: number, userId: number, text: string) {
    super(id);
    this.chatId = chatId;
    this.userId = userId;
    this.text = text;
    this.timestamp = new Date();
  }

  getChatId(): number {
    return this.chatId;
  }

  getUserId(): number {
    return this.userId;
  }

  getText(): string {
    return this.text;
  }

  getTimestamp(): Date {
    return this.timestamp;
  }

  markAsSent(): void {
    this.apply(new MessageSentEvent(this.getId(), this.chatId, this.userId));
  }
}
