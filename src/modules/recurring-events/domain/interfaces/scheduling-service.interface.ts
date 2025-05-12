import { FileEventData } from '../../../../shared/domain/models/file-event.model';

export type TimeEventCallback = (eventId: string) => Promise<void> | void;
export type FileEventCallback = (eventData: FileEventData) => Promise<void> | void;

export interface ISchedulingService {
  scheduleDaily(timeStr: string, eventId: string, callback: TimeEventCallback): void;

  scheduleWeekly(
    weekdayStr: string,
    timeStr: string,
    eventId: string,
    callback: TimeEventCallback,
  ): void;

  scheduleInterval(
    interval: number,
    unit: string,
    eventId: string,
    callback: TimeEventCallback,
  ): void;

  addJob(scheduleDsl: string, eventId: string, callback: TimeEventCallback): boolean;

  unschedule(eventId: string): void;

  watchDirectory(path: string, callback: FileEventCallback): void;

  start(): void;

  stop(): void;
}
