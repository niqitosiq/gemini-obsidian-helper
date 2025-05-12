import { Injectable, OnModuleDestroy } from '@nestjs/common';
import {
  ISchedulingService,
  TimeEventCallback,
  FileEventCallback,
} from '../../domain/interfaces/scheduling-service.interface';
import * as schedule from 'node-schedule';
import * as chokidar from 'chokidar';
import * as path from 'path';
import { FileEventData } from '../../../../shared/domain/models/file-event.model';

@Injectable()
export class SchedulingService implements ISchedulingService, OnModuleDestroy {
  private jobs: Map<string, schedule.Job> = new Map();
  private watchers: Map<string, chokidar.FSWatcher> = new Map();
  private isRunning = false;

  scheduleDaily(timeStr: string, eventId: string, callback: TimeEventCallback): void {
    const rule = new schedule.RecurrenceRule();
    const [hours, minutes] = timeStr.split(':').map(Number);

    rule.hour = hours;
    rule.minute = minutes;

    this.scheduleJob(eventId, rule, callback);
  }

  scheduleWeekly(
    weekdayStr: string,
    timeStr: string,
    eventId: string,
    callback: TimeEventCallback,
  ): void {
    const rule = new schedule.RecurrenceRule();
    const [hours, minutes] = timeStr.split(':').map(Number);

    rule.hour = hours;
    rule.minute = minutes;

    // Map weekday string to number (0 = Sunday, 1 = Monday, etc.)
    const weekdayMap: Record<string, number> = {
      sunday: 0,
      monday: 1,
      tuesday: 2,
      wednesday: 3,
      thursday: 4,
      friday: 5,
      saturday: 6,
    };

    const dayNum = weekdayMap[weekdayStr.toLowerCase()];
    if (dayNum === undefined) {
      console.error(`Invalid weekday: ${weekdayStr}`);
      return;
    }

    rule.dayOfWeek = dayNum;

    this.scheduleJob(eventId, rule, callback);
  }

  scheduleInterval(
    interval: number,
    unit: string,
    eventId: string,
    callback: TimeEventCallback,
  ): void {
    let milliseconds: number;

    switch (unit.toLowerCase()) {
      case 'minutes':
      case 'minute':
      case 'mins':
      case 'min':
        milliseconds = interval * 60 * 1000;
        break;
      case 'hours':
      case 'hour':
        milliseconds = interval * 60 * 60 * 1000;
        break;
      case 'days':
      case 'day':
        milliseconds = interval * 24 * 60 * 60 * 1000;
        break;
      default:
        console.error(`Invalid interval unit: ${unit}`);
        return;
    }

    const job = setInterval(() => {
      callback(eventId);
    }, milliseconds);

    // Store the interval ID as a Job object for consistency
    this.jobs.set(eventId, {
      cancel: () => clearInterval(job),
      nextInvocation: () => new Date(Date.now() + milliseconds),
    } as any);
  }

  addJob(scheduleDsl: string, eventId: string, callback: TimeEventCallback): boolean {
    // Parse the DSL string to determine the type of schedule
    const dailyPattern = /^daily at (\d{1,2}:\d{2})$/i;
    const weeklyPattern = /^every (\w+) at (\d{1,2}:\d{2})$/i;
    const intervalPattern = /^every (\d+) (minutes?|hours?|days?)$/i;

    let match;

    if ((match = dailyPattern.exec(scheduleDsl))) {
      const timeStr = match[1];
      this.scheduleDaily(timeStr, eventId, callback);
      return true;
    } else if ((match = weeklyPattern.exec(scheduleDsl))) {
      const weekdayStr = match[1];
      const timeStr = match[2];
      this.scheduleWeekly(weekdayStr, timeStr, eventId, callback);
      return true;
    } else if ((match = intervalPattern.exec(scheduleDsl))) {
      const interval = parseInt(match[1], 10);
      const unit = match[2];
      this.scheduleInterval(interval, unit, eventId, callback);
      return true;
    }

    console.error(`Invalid schedule DSL: ${scheduleDsl}`);
    return false;
  }

  unschedule(eventId: string): void {
    const job = this.jobs.get(eventId);
    if (job) {
      job.cancel();
      this.jobs.delete(eventId);
    }
  }

  watchDirectory(directoryPath: string, callback: FileEventCallback): void {
    if (this.watchers.has(directoryPath)) {
      console.log(`Already watching directory: ${directoryPath}`);
      return;
    }

    try {
      const watcher = chokidar.watch(directoryPath, {
        persistent: true,
        ignoreInitial: true,
        awaitWriteFinish: {
          stabilityThreshold: 2000,
          pollInterval: 100,
        },
      });

      watcher
        .on('add', (filePath) => {
          const eventData: FileEventData = {
            eventType: 'add',
            srcPath: filePath,
            isDirectory: false,
          };
          callback(eventData);
        })
        .on('change', (filePath) => {
          const eventData: FileEventData = {
            eventType: 'change',
            srcPath: filePath,
            isDirectory: false,
          };
          callback(eventData);
        })
        .on('unlink', (filePath) => {
          const eventData: FileEventData = {
            eventType: 'unlink',
            srcPath: filePath,
            isDirectory: false,
          };
          callback(eventData);
        })
        .on('addDir', (dirPath) => {
          const eventData: FileEventData = {
            eventType: 'addDir',
            srcPath: dirPath,
            isDirectory: true,
          };
          callback(eventData);
        })
        .on('unlinkDir', (dirPath) => {
          const eventData: FileEventData = {
            eventType: 'unlinkDir',
            srcPath: dirPath,
            isDirectory: true,
          };
          callback(eventData);
        })
        .on('error', (error) => {
          console.error(`Watcher error: ${error}`);
        });

      this.watchers.set(directoryPath, watcher);
      console.log(`Started watching directory: ${directoryPath}`);
    } catch (error) {
      console.error(`Error setting up directory watcher for ${directoryPath}:`, error);
    }
  }

  start(): void {
    this.isRunning = true;
    console.log('Scheduling service started');
  }

  stop(): void {
    // Cancel all scheduled jobs
    this.jobs.forEach((job, eventId) => {
      job.cancel();
    });
    this.jobs.clear();

    // Close all file watchers
    this.watchers.forEach((watcher, dirPath) => {
      watcher.close();
    });
    this.watchers.clear();

    this.isRunning = false;
    console.log('Scheduling service stopped');
  }

  onModuleDestroy(): void {
    this.stop();
  }

  private scheduleJob(
    eventId: string,
    rule: schedule.RecurrenceRule,
    callback: TimeEventCallback,
  ): void {
    // Cancel existing job with the same ID
    this.unschedule(eventId);

    // Schedule the new job
    const job = schedule.scheduleJob(rule, () => {
      callback(eventId);
    });

    this.jobs.set(eventId, job);
  }
}
