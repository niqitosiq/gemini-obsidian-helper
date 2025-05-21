import { Entity } from '../../../../core/ddd/entity';

export enum TaskStatus {
  TODO = 'todo',
  IN_PROGRESS = 'in progress',
  WAITING = 'waiting',
  DONE = 'done',
}

export enum TaskPriority {
  HIGHEST = 1,
  HIGH = 2,
  MEDIUM = 3,
  LOW = 4,
  LOWEST = 5,
}

export interface TaskReminder {
  minutesBefore: number;
  message?: string;
}

export interface TaskData {
  title: string;
  description?: string;
  date?: Date;
  endDate?: Date;
  startTime?: string;
  endTime?: string;
  duration?: string;
  completed: boolean;
  status: TaskStatus;
  priority?: TaskPriority;
  allDay: boolean;
  type: 'single' | 'recurring';
  dependsOn?: string[];
  blocks?: string[];
  reminders?: TaskReminder[];
  filePath: string;
  schedule?: string;
}

export class Task extends Entity<string> {
  private readonly title: string;
  private readonly description: string;
  private readonly date?: Date;
  private readonly endDate?: Date;
  private readonly startTime?: string;
  private readonly endTime?: string;
  private readonly duration?: string;
  private readonly completed: boolean;
  private readonly status: TaskStatus;
  private readonly priority?: TaskPriority;
  private readonly allDay: boolean;
  private readonly type: 'single' | 'recurring';
  private readonly dependsOn: string[];
  private readonly blocks: string[];
  private readonly reminders: TaskReminder[];
  private readonly filePath: string;
  private readonly schedule?: string;

  constructor(id: string, data: TaskData) {
    super(id);
    this.title = data.title;
    this.description = data.description || '';
    this.date = data.date;
    this.endDate = data.endDate;
    this.startTime = data.startTime;
    this.endTime = data.endTime;
    this.duration = data.duration;
    this.completed = data.completed;
    this.status = data.status;
    this.priority = data.priority;
    this.allDay = data.allDay;
    this.type = data.type;
    this.dependsOn = data.dependsOn || [];
    this.blocks = data.blocks || [];
    this.reminders = data.reminders || [];
    this.filePath = data.filePath;
    this.schedule = data.schedule;
  }

  getTitle(): string {
    return this.title;
  }

  getDescription(): string {
    return this.description;
  }

  getDate(): Date | undefined {
    return this.date;
  }

  getEndDate(): Date | undefined {
    return this.endDate;
  }

  getStartTime(): string | undefined {
    return this.startTime;
  }

  getEndTime(): string | undefined {
    return this.endTime;
  }

  getDuration(): string | undefined {
    return this.duration;
  }

  isCompleted(): boolean {
    return this.completed;
  }

  getStatus(): TaskStatus {
    return this.status;
  }

  getPriority(): TaskPriority | undefined {
    return this.priority;
  }

  isAllDay(): boolean {
    return this.allDay;
  }

  getType(): 'single' | 'recurring' {
    return this.type;
  }

  getDependsOn(): string[] {
    return this.dependsOn;
  }

  getBlocks(): string[] {
    return this.blocks;
  }

  getReminders(): TaskReminder[] {
    return this.reminders;
  }

  getFilePath(): string {
    return this.filePath;
  }

  getSchedule(): string | undefined {
    return this.schedule;
  }

  toObject(): TaskData {
    return {
      title: this.title,
      description: this.description,
      date: this.date,
      endDate: this.endDate,
      startTime: this.startTime,
      endTime: this.endTime,
      duration: this.duration,
      completed: this.completed,
      status: this.status,
      priority: this.priority,
      allDay: this.allDay,
      type: this.type,
      dependsOn: this.dependsOn,
      blocks: this.blocks,
      reminders: this.reminders,
      filePath: this.filePath,
      schedule: this.schedule,
    };
  }
}
