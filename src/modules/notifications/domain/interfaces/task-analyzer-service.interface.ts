import { Task } from '../models/task.model';

export interface ITaskAnalyzerService {
  /**
   * Get all tasks scheduled for today
   *
   * @returns Promise resolving to an array of tasks for today
   */
  getTodaysTasks(): Promise<Task[]>;

  /**
   * Get all tasks that are overdue (past due date but not completed)
   *
   * @returns Promise resolving to an array of overdue tasks
   */
  getOverdueTasks(): Promise<Task[]>;

  /**
   * Get all tasks that are completed today
   *
   * @returns Promise resolving to an array of tasks completed today
   */
  getCompletedTasksToday(): Promise<Task[]>;

  /**
   * Get all tasks that are postponed (moved from an earlier date to a future date)
   *
   * @returns Promise resolving to an array of postponed tasks
   */
  getPostponedTasks(): Promise<Task[]>;

  /**
   * Get tasks that are scheduled for a specific date
   *
   * @param date - The date to get tasks for
   * @returns Promise resolving to an array of tasks for the specified date
   */
  getTasksForDate(date: Date): Promise<Task[]>;
}
