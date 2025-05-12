/**
 * Interface for the scheduling service
 */
export interface ISchedulingService {
  /**
   * Add a job to the schedule
   *
   * @param cronExpression - Cron expression for the job timing
   * @param jobId - Unique identifier for the job
   * @param callback - Function to execute when the job runs
   * @returns void
   */
  addJob(cronExpression: string, jobId: string, callback: () => void): void;

  /**
   * Remove a job from the schedule
   *
   * @param jobId - Unique identifier for the job to remove
   * @returns boolean - True if the job was found and removed, false otherwise
   */
  unschedule(jobId: string): boolean;

  /**
   * Get a list of all scheduled job IDs
   *
   * @returns Array of job IDs
   */
  getScheduledJobs(): string[];
}
