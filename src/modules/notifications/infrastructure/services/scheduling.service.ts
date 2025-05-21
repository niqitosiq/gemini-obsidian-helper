import { Injectable, Logger } from '@nestjs/common';
import { ISchedulingService } from '../../domain/interfaces/scheduling-service.interface';
import { SchedulerRegistry } from '@nestjs/schedule';
import { Timeout, Interval } from '@nestjs/schedule';

/**
 * Implementation of the scheduling service using NestJS SchedulerRegistry
 */
@Injectable()
export class SchedulingService implements ISchedulingService {
  private readonly logger = new Logger(SchedulingService.name);
  private readonly jobs = new Map<string, { intervalId: any; callback: () => void }>();

  constructor(private schedulerRegistry: SchedulerRegistry) {}

  /**
   * Add a job to the schedule
   *
   * @param cronExpression - Cron expression for the job timing
   * @param jobId - Unique identifier for the job
   * @param callback - Function to execute when the job runs
   */
  addJob(cronExpression: string, jobId: string, callback: () => void): void {
    try {
      // Handle special case for "daily at HH:MM" format
      if (cronExpression.startsWith('daily at ')) {
        const timeStr = cronExpression.substring('daily at '.length);
        const [hours, minutes] = timeStr.split(':').map(Number);

        if (
          isNaN(hours) ||
          isNaN(minutes) ||
          hours < 0 ||
          hours > 23 ||
          minutes < 0 ||
          minutes > 59
        ) {
          throw new Error(`Invalid time format: ${timeStr}`);
        }

        // Calculate the time until the next occurrence
        const now = new Date();
        const targetTime = new Date(now);
        targetTime.setHours(hours, minutes, 0, 0);

        // If the target time is in the past for today, schedule for tomorrow
        if (targetTime <= now) {
          targetTime.setDate(targetTime.getDate() + 1);
        }

        const timeUntilTarget = targetTime.getTime() - now.getTime();

        // Unschedule existing job with the same ID if it exists
        this.unschedule(jobId);

        // First occurrence: Schedule a one-time execution
        const timeoutId = setTimeout(() => {
          this.logger.log(`Executing scheduled job: ${jobId}`);
          try {
            callback();
          } catch (error) {
            this.logger.error(
              `Error executing scheduled job ${jobId}: ${error.message}`,
              error.stack,
            );
          }

          // Then set up a daily interval for subsequent executions
          const intervalId = setInterval(
            () => {
              this.logger.log(`Executing scheduled job: ${jobId}`);
              try {
                callback();
              } catch (error) {
                this.logger.error(
                  `Error executing scheduled job ${jobId}: ${error.message}`,
                  error.stack,
                );
              }
            },
            24 * 60 * 60 * 1000,
          ); // 24 hours

          // Store the interval ID for future reference
          this.jobs.set(jobId, { intervalId, callback });

          // Add to NestJS registry for proper cleanup
          this.schedulerRegistry.addInterval(jobId, intervalId);
        }, timeUntilTarget);

        // Store the timeout ID temporarily
        this.jobs.set(jobId, { intervalId: timeoutId, callback });

        // Add to NestJS registry for proper cleanup
        this.schedulerRegistry.addTimeout(jobId, timeoutId);

        this.logger.log(`Job scheduled: ${jobId} for ${targetTime.toISOString()}`);
      } else {
        throw new Error(
          `Unsupported cron expression format: ${cronExpression}. Only 'daily at HH:MM' format is supported.`,
        );
      }
    } catch (error) {
      this.logger.error(`Error scheduling job ${jobId}: ${error.message}`, error.stack);
      throw error;
    }
  }

  /**
   * Remove a job from the schedule
   *
   * @param jobId - Unique identifier for the job to remove
   * @returns boolean - True if the job was found and removed, false otherwise
   */
  unschedule(jobId: string): boolean {
    try {
      const job = this.jobs.get(jobId);
      if (job) {
        // Clear the timeout or interval
        clearTimeout(job.intervalId);
        clearInterval(job.intervalId);

        // Remove from registry
        try {
          this.schedulerRegistry.deleteTimeout(jobId);
        } catch (e) {
          // Ignore if it wasn't a timeout
        }

        try {
          this.schedulerRegistry.deleteInterval(jobId);
        } catch (e) {
          // Ignore if it wasn't an interval
        }

        // Remove from our map
        this.jobs.delete(jobId);
        this.logger.log(`Job unscheduled: ${jobId}`);
        return true;
      }
      return false;
    } catch (error) {
      this.logger.error(`Error unscheduling job ${jobId}: ${error.message}`, error.stack);
      return false;
    }
  }

  /**
   * Get a list of all scheduled job IDs
   *
   * @returns Array of job IDs
   */
  getScheduledJobs(): string[] {
    return Array.from(this.jobs.keys());
  }
}
