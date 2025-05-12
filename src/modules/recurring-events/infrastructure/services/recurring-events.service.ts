import { Injectable, Inject, OnModuleDestroy } from '@nestjs/common';
import { IRecurringEventsEngine } from '../../domain/interfaces/recurring-events.interface';
import { ISchedulingService } from '../../domain/interfaces/scheduling-service.interface';
import { IVaultService } from '../../../vault/domain/interfaces/vault-service.interface';
import { ITelegramService } from '../../../telegram/domain/interfaces/telegram-service.interface';
import { ConfigService } from '../../../../shared/infrastructure/config/config.service';
import { Event, EventType, EventData } from '../../domain/entities/event.entity';
import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'yaml';
import { v4 as uuidv4 } from 'uuid';

const DEFAULT_TASKS_DIR_RELATIVE = '03 - Tasks';
const GLOBAL_EVENTS_CONFIG_PATH = 'global_recurring_events.json';

@Injectable()
export class RecurringEventsService implements IRecurringEventsEngine, OnModuleDestroy {
  private events: Map<string, Event> = new Map();
  private scheduledFileEventIds: Set<string> = new Set();
  private lastProcessed: Map<string, Date> = new Map();
  private readonly debounceInterval: number = 1000; // 1 second debounce

  constructor(
    @Inject('ISchedulingService') private readonly schedulingService: ISchedulingService,
    @Inject('IVaultService') private readonly vaultService: IVaultService,
    @Inject('ITelegramService') private readonly telegramService: ITelegramService,
    private readonly configService: ConfigService,
  ) {}

  async loadAndScheduleAll(): Promise<void> {
    console.log('Loading and scheduling all recurring events...');
    this.events.clear();
    this.scheduledFileEventIds.clear();

    // Load global events
    await this.loadGlobalEvents();

    // Schedule global events
    for (const [eventId, event] of this.events.entries()) {
      if (event.isGlobalEvent()) {
        this.scheduleEvent(eventId, event);
      }
    }

    // Load vault tasks
    await this.loadVaultTasks();

    console.log('Finished loading and scheduling events.');
  }

  async start(): Promise<void> {
    await this.loadAndScheduleAll();

    // Schedule daily rescheduling at 00:01
    this.schedulingService.addJob('daily at 00:01', 'daily_reschedule_vault_tasks', () =>
      this.loadAndScheduleAll(),
    );

    this.schedulingService.start();
    console.log('RecurringEventsEngine started.');
  }

  async stop(): Promise<void> {
    console.log('Stopping RecurringEventsEngine...');
    this.schedulingService.stop();
    console.log('RecurringEventsEngine stopped.');
  }

  async handleVaultFileEvent(relativePath: string): Promise<void> {
    const now = new Date();
    const lastProcessTime = this.lastProcessed.get(relativePath);

    // Skip if file was processed recently
    if (lastProcessTime && now.getTime() - lastProcessTime.getTime() < this.debounceInterval) {
      console.log(`Skipping duplicate event for ${relativePath} (debounced)`);
      return;
    }

    // Update last processed time
    this.lastProcessed.set(relativePath, now);

    // Process the file event
    await this.processVaultFileEvent(relativePath);
  }

  async onModuleDestroy(): Promise<void> {
    await this.stop();
  }

  // Private methods

  private async loadGlobalEvents(): Promise<void> {
    try {
      const globalEventsPath = path.join(process.cwd(), GLOBAL_EVENTS_CONFIG_PATH);
      if (!fs.existsSync(globalEventsPath)) {
        console.log(`Global events file not found at ${globalEventsPath}`);
        return;
      }

      const fileContent = await fs.promises.readFile(globalEventsPath, 'utf8');
      const eventsData = JSON.parse(fileContent);

      if (!Array.isArray(eventsData)) {
        console.error('Global events file does not contain an array');
        return;
      }

      for (const eventData of eventsData) {
        const eventId = eventData.id || uuidv4();
        if (this.validateEventData(eventId, eventData)) {
          const event = new Event(eventId, {
            ...eventData,
            isGlobal: true,
          });
          this.events.set(eventId, event);
        }
      }

      console.log(`Loaded ${this.events.size} global events`);
    } catch (error) {
      console.error('Error loading global events:', error);
    }
  }

  private async loadVaultTasks(): Promise<void> {
    const vaultRoot = this.vaultService.getVaultRoot();
    if (!vaultRoot) {
      console.error('Vault root path is not configured');
      return;
    }

    const tasksDir = path.join(vaultRoot, DEFAULT_TASKS_DIR_RELATIVE);
    if (!(await this.vaultService.folderExists(DEFAULT_TASKS_DIR_RELATIVE))) {
      console.error(`Tasks directory not found at ${tasksDir}`);
      return;
    }

    // Set up watchdog for vault tasks directory
    this.schedulingService.watchDirectory(tasksDir, (eventData) => {
      // Convert absolute path to relative path within the vault
      try {
        const relativePath = path.relative(vaultRoot, eventData.srcPath);

        // Ensure the relative path is correctly formatted and within the tasks directory
        if (
          !relativePath.startsWith(DEFAULT_TASKS_DIR_RELATIVE + path.sep) &&
          relativePath !== DEFAULT_TASKS_DIR_RELATIVE
        ) {
          return;
        }

        // Handle the file event
        this.handleVaultFileEvent(relativePath).catch((error) => {
          console.error(`Error handling vault file event for ${relativePath}:`, error);
        });
      } catch (error) {
        console.error(`Error processing file event for ${eventData.srcPath}:`, error);
      }
    });

    // Scan for task files
    const files = await this.vaultService.listFiles(DEFAULT_TASKS_DIR_RELATIVE);
    if (!files) {
      return;
    }

    for (const file of files) {
      if (file.endsWith('.md')) {
        const relativePath = path.join(DEFAULT_TASKS_DIR_RELATIVE, file);
        await this.processVaultFileEvent(relativePath);
      }
    }
  }

  private async processVaultFileEvent(relativePath: string): Promise<void> {
    // Unschedule any existing events for this file
    this.unscheduleFileEvents(relativePath);

    // Skip if file doesn't exist or isn't a markdown file
    if (!relativePath.endsWith('.md') || !(await this.vaultService.fileExists(relativePath))) {
      return;
    }

    // Read and parse the file
    const content = await this.vaultService.readFile(relativePath);
    if (!content) {
      return;
    }

    // Extract frontmatter
    const frontmatter = this.extractFrontmatter(content);
    if (!frontmatter) {
      return;
    }

    // Parse task details
    const taskDetails = this.extractTaskDetails(frontmatter);
    if (!taskDetails) {
      return;
    }

    // Create events for the task
    this.createEventsFromTask(taskDetails, relativePath);
  }

  private extractFrontmatter(content: string): Record<string, any> | null {
    const frontmatterRegex = /^---\s*\n([\s\S]*?)\n---\s*\n/;
    const match = content.match(frontmatterRegex);

    if (!match || !match[1]) {
      return null;
    }

    try {
      return yaml.parse(match[1]);
    } catch (error) {
      console.error('Error parsing frontmatter:', error);
      return null;
    }
  }

  private extractTaskDetails(frontmatter: Record<string, any>): Record<string, any> | null {
    // Check for required fields
    if (!frontmatter.schedule) {
      return null;
    }

    return {
      schedule: frontmatter.schedule,
      message: frontmatter.message || frontmatter.title || 'Task reminder',
      reminders: frontmatter.reminders,
    };
  }

  private createEventsFromTask(taskDetails: Record<string, any>, relativePath: string): void {
    const { schedule, message, reminders } = taskDetails;

    // Create the main event
    const eventId = `task_${uuidv4()}`;
    const eventData: EventData = {
      type: this.determineEventType(schedule),
      message,
      taskPath: relativePath,
    };

    // Add type-specific properties
    switch (eventData.type) {
      case EventType.DAILY:
        eventData.time = schedule.replace(/^daily at /i, '');
        break;
      case EventType.WEEKLY:
        const match = schedule.match(/^every (\w+) at (\d{1,2}:\d{2})$/i);
        if (match) {
          eventData.weekday = match[1];
          eventData.time = match[2];
        }
        break;
      case EventType.INTERVAL:
        const intervalMatch = schedule.match(/^every (\d+) (minutes?|hours?|days?)$/i);
        if (intervalMatch) {
          eventData.interval = parseInt(intervalMatch[1], 10);
          eventData.unit = intervalMatch[2];
        }
        break;
    }

    // Create and schedule the event
    const event = new Event(eventId, eventData);
    this.events.set(eventId, event);
    this.scheduleEvent(eventId, event);
    this.scheduledFileEventIds.add(eventId);

    // Create reminder events if specified
    if (reminders && Array.isArray(reminders)) {
      for (const reminder of reminders) {
        const reminderId = `reminder_${uuidv4()}`;
        const reminderData: EventData = {
          ...eventData,
          message: `Reminder: ${message}`,
        };

        // Adjust reminder time based on the main event
        // This is a simplified implementation

        const reminderEvent = new Event(reminderId, reminderData);
        this.events.set(reminderId, reminderEvent);
        this.scheduleEvent(reminderId, reminderEvent);
        this.scheduledFileEventIds.add(reminderId);
      }
    }
  }

  private determineEventType(schedule: string): EventType {
    if (/^daily at/i.test(schedule)) {
      return EventType.DAILY;
    } else if (/^every \w+ at/i.test(schedule)) {
      return EventType.WEEKLY;
    } else if (/^every \d+ (minutes?|hours?|days?)$/i.test(schedule)) {
      return EventType.INTERVAL;
    }

    // Default to daily if unknown
    return EventType.DAILY;
  }

  private unscheduleFileEvents(relativePath: string): void {
    // Find and unschedule all events related to this file
    for (const [eventId, event] of this.events.entries()) {
      if (event.getTaskPath() === relativePath) {
        this.schedulingService.unschedule(eventId);
        this.events.delete(eventId);
        this.scheduledFileEventIds.delete(eventId);
      }
    }
  }

  private scheduleEvent(eventId: string, event: Event): void {
    const eventData = event.toObject();

    switch (eventData.type) {
      case EventType.DAILY:
        if (eventData.time) {
          this.schedulingService.scheduleDaily(eventData.time, eventId, (id) =>
            this.handleTimeEvent(id),
          );
        }
        break;
      case EventType.WEEKLY:
        if (eventData.weekday && eventData.time) {
          this.schedulingService.scheduleWeekly(eventData.weekday, eventData.time, eventId, (id) =>
            this.handleTimeEvent(id),
          );
        }
        break;
      case EventType.INTERVAL:
        if (eventData.interval !== undefined && eventData.unit) {
          this.schedulingService.scheduleInterval(
            eventData.interval,
            eventData.unit,
            eventId,
            (id) => this.handleTimeEvent(id),
          );
        }
        break;
    }
  }

  private async handleTimeEvent(eventId: string): Promise<void> {
    const event = this.events.get(eventId);
    if (!event) {
      console.error(`Event ${eventId} not found`);
      return;
    }

    await this.executeEvent(eventId, event);
  }

  private async executeEvent(eventId: string, event: Event): Promise<void> {
    const eventData = event.toObject();

    // Get user IDs from config
    const userIds = this.configService.getTelegramUserIds();

    // Send message to all configured users
    for (const userId of userIds) {
      try {
        const numericUserId = parseInt(userId, 10);
        if (!isNaN(numericUserId)) {
          await this.telegramService.sendMessageToUser(
            numericUserId,
            eventData.message,
            'Markdown',
          );
        }
      } catch (error) {
        console.error(`Error sending event message to user ${userId}:`, error);
      }
    }
  }

  private validateEventData(eventId: string, data: any): boolean {
    if (!data) {
      console.error(`Invalid event data for ${eventId}: data is null or undefined`);
      return false;
    }

    if (!data.type) {
      console.error(`Invalid event data for ${eventId}: missing type`);
      return false;
    }

    if (!data.message) {
      console.error(`Invalid event data for ${eventId}: missing message`);
      return false;
    }

    switch (data.type) {
      case EventType.DAILY:
        if (!data.time) {
          console.error(`Invalid daily event data for ${eventId}: missing time`);
          return false;
        }
        break;
      case EventType.WEEKLY:
        if (!data.weekday || !data.time) {
          console.error(`Invalid weekly event data for ${eventId}: missing weekday or time`);
          return false;
        }
        break;
      case EventType.INTERVAL:
        if (data.interval === undefined || !data.unit) {
          console.error(`Invalid interval event data for ${eventId}: missing interval or unit`);
          return false;
        }
        break;
      default:
        console.error(`Invalid event type for ${eventId}: ${data.type}`);
        return false;
    }

    return true;
  }
}
