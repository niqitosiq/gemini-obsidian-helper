import { Entity } from '../../../../core/ddd/entity';

export enum EventType {
  DAILY = 'daily',
  WEEKLY = 'weekly',
  INTERVAL = 'interval',
}

export interface EventData {
  type: EventType;
  time?: string;
  weekday?: string;
  interval?: number;
  unit?: string;
  message: string;
  isGlobal?: boolean;
  taskPath?: string;
}

export class Event extends Entity<string> {
  private readonly type: EventType;
  private readonly time?: string;
  private readonly weekday?: string;
  private readonly interval?: number;
  private readonly unit?: string;
  private readonly message: string;
  private readonly isGlobal: boolean;
  private readonly taskPath?: string;

  constructor(id: string, data: EventData) {
    super(id);
    this.type = data.type;
    this.time = data.time;
    this.weekday = data.weekday;
    this.interval = data.interval;
    this.unit = data.unit;
    this.message = data.message;
    this.isGlobal = data.isGlobal || false;
    this.taskPath = data.taskPath;
  }

  getType(): EventType {
    return this.type;
  }

  getTime(): string | undefined {
    return this.time;
  }

  getWeekday(): string | undefined {
    return this.weekday;
  }

  getInterval(): number | undefined {
    return this.interval;
  }

  getUnit(): string | undefined {
    return this.unit;
  }

  getMessage(): string {
    return this.message;
  }

  isGlobalEvent(): boolean {
    return this.isGlobal;
  }

  getTaskPath(): string | undefined {
    return this.taskPath;
  }

  toObject(): EventData {
    return {
      type: this.type,
      time: this.time,
      weekday: this.weekday,
      interval: this.interval,
      unit: this.unit,
      message: this.message,
      isGlobal: this.isGlobal,
      taskPath: this.taskPath,
    };
  }
}
