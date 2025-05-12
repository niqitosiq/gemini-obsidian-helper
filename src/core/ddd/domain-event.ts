export abstract class DomainEvent {
  public readonly eventId: string;
  public readonly occurredOn: Date;

  constructor() {
    this.eventId = this.generateId();
    this.occurredOn = new Date();
  }

  private generateId(): string {
    return (
      Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15)
    );
  }
}
