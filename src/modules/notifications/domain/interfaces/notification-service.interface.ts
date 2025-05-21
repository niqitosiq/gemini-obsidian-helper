import { Task } from '../models/task.model';

export interface INotificationService {
  /**
   * Send a reminder for a specific task
   *
   * @param task - The task to send a reminder for
   * @param minutesBefore - How many minutes before the task start time to send the reminder
   * @returns Promise resolving to boolean indicating success
   */
  sendTaskReminder(task: Task, minutesBefore?: number): Promise<boolean>;

  /**
   * Send a morning digest of today's tasks
   *
   * @param userId - The user ID to send the digest to
   * @returns Promise resolving to boolean indicating success
   */
  sendMorningDigest(userId: number): Promise<boolean>;

  /**
   * Send an evening check-in to review completed and postponed tasks
   *
   * @param userId - The user ID to send the check-in to
   * @returns Promise resolving to boolean indicating success
   */
  sendEveningCheckIn(userId: number): Promise<boolean>;

  /**
   * Schedule reminders for a task
   *
   * @param task - The task to schedule reminders for
   * @returns Promise resolving to void
   */
  scheduleRemindersForTask(task: Task): Promise<void>;

  /**
   * Reset and reschedule all reminders for today's tasks
   * This is typically called at midnight to refresh the notification schedule
   *
   * @returns Promise resolving to void
   */
  resetAndRescheduleAllReminders(): Promise<void>;
}
