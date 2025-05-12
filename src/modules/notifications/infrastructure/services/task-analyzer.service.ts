import { Injectable, Inject, Logger } from '@nestjs/common';
import { ITaskAnalyzerService } from '../../domain/interfaces/task-analyzer-service.interface';
import { Task, TaskData, TaskStatus } from '../../domain/models/task.model';
import { IVaultService } from '../../../vault/domain/interfaces/vault-service.interface';
import * as yaml from 'yaml';
import * as path from 'path';

@Injectable()
export class TaskAnalyzerService implements ITaskAnalyzerService {
  private readonly logger = new Logger(TaskAnalyzerService.name);
  private readonly tasksFolder = '03 - Tasks';

  constructor(@Inject('IVaultService') private readonly vaultService: IVaultService) {}

  async getTodaysTasks(): Promise<Task[]> {
    const today = new Date();
    return this.getTasksForDate(today);
  }

  async getOverdueTasks(): Promise<Task[]> {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const allTasks = await this.getAllTasks();

    return allTasks.filter((task) => {
      const taskDate = task.getDate();
      return !task.isCompleted() && taskDate instanceof Date && taskDate < today;
    });
  }

  async getCompletedTasksToday(): Promise<Task[]> {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    const allTasks = await this.getAllTasks();

    return allTasks.filter(
      (task) =>
        task.isCompleted() &&
        task.getDate() instanceof Date &&
        task.getDate()! >= today &&
        task.getDate()! < tomorrow,
    );
  }

  async getPostponedTasks(): Promise<Task[]> {
    // This would require tracking task history, which isn't currently implemented
    // For now, we'll return tasks that are marked with a status of 'waiting'
    const allTasks = await this.getAllTasks();

    return allTasks.filter(
      (task) => !task.isCompleted() && task.getStatus() === TaskStatus.WAITING,
    );
  }

  async getTasksForDate(date: Date): Promise<Task[]> {
    const targetDate = new Date(date);
    targetDate.setHours(0, 0, 0, 0);

    const nextDate = new Date(targetDate);
    nextDate.setDate(nextDate.getDate() + 1);

    const allTasks = await this.getAllTasks();

    return allTasks.filter((task) => {
      const taskDate = task.getDate();
      return taskDate instanceof Date && taskDate >= targetDate && taskDate < nextDate;
    });
  }

  private async getAllTasks(): Promise<Task[]> {
    try {
      // Check if tasks folder exists
      if (!(await this.vaultService.folderExists(this.tasksFolder))) {
        this.logger.warn(`Tasks folder '${this.tasksFolder}' not found in vault`);
        return [];
      }

      // Get all markdown files in the tasks folder
      const files = await this.vaultService.listFiles(this.tasksFolder);
      if (!files || files.length === 0) {
        return [];
      }

      const tasks: Task[] = [];

      // Process each file
      for (const file of files) {
        if (!file.endsWith('.md')) continue;

        const filePath = path.join(this.tasksFolder, file);
        const content = await this.vaultService.readFile(filePath);

        if (!content) continue;

        const task = this.parseTaskFromContent(content, filePath);
        if (task) {
          tasks.push(task);
        }
      }

      return tasks;
    } catch (error) {
      this.logger.error(`Error getting all tasks: ${error.message}`, error.stack);
      return [];
    }
  }

  private parseTaskFromContent(content: string, filePath: string): Task | null {
    try {
      // Extract frontmatter
      const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
      if (!frontmatterMatch) return null;

      const frontmatter = yaml.parse(frontmatterMatch[1]);
      if (!frontmatter) return null;

      // Parse dates
      let date: Date | undefined;
      let endDate: Date | undefined;

      if (frontmatter.date) {
        date = new Date(frontmatter.date);
      }

      if (frontmatter.endDate) {
        endDate = new Date(frontmatter.endDate);
      }

      // Create task data
      const taskData: TaskData = {
        title: frontmatter.title || path.basename(filePath, '.md'),
        description: this.extractDescription(content),
        date,
        endDate,
        startTime: frontmatter.startTime,
        endTime: frontmatter.endTime,
        duration: frontmatter.duration,
        completed: frontmatter.completed === true,
        status: frontmatter.status || TaskStatus.TODO,
        priority: frontmatter.priority,
        allDay: frontmatter.allDay === true,
        type: frontmatter.type || 'single',
        dependsOn: frontmatter.depends_on || [],
        blocks: frontmatter.blocks || [],
        reminders: frontmatter.reminders || [],
        filePath,
        schedule: frontmatter.schedule,
      };

      return new Task(this.generateId(), taskData);
    } catch (error) {
      this.logger.error(`Error parsing task from ${filePath}: ${error.message}`);
      return null;
    }
  }

  private extractDescription(content: string): string {
    // Remove frontmatter
    const withoutFrontmatter = content.replace(/^---\n[\s\S]*?\n---/, '').trim();

    // Look for description section
    const descriptionMatch = withoutFrontmatter.match(/## 📝 Описание\s*([\s\S]*?)(?:$|(?:\n## ))/);

    if (descriptionMatch && descriptionMatch[1]) {
      return descriptionMatch[1].trim();
    }

    return withoutFrontmatter;
  }

  // Simple UUID generator
  private generateId(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
}
