export interface IEventHandler<TEvent> {
  handle(event: TEvent): Promise<void>;
}

export abstract class EventHandler<TEvent> implements IEventHandler<TEvent> {
  abstract handle(event: TEvent): Promise<void>;
}
