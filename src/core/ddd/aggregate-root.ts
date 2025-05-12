import { Entity } from './entity';
import { DomainEvent } from './domain-event';

export abstract class AggregateRoot<T> extends Entity<T> {
  private domainEvents: DomainEvent[] = [];

  public getDomainEvents(): DomainEvent[] {
    return [...this.domainEvents];
  }

  public clearEvents(): void {
    this.domainEvents = [];
  }

  protected apply(event: DomainEvent): void {
    this.domainEvents.push(event);
  }
}
