import { Inject, Injectable, Logger, OnModuleInit, forwardRef } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { INotificationService } from '../../domain/interfaces/notification-service.interface';
import { ITaskAnalyzerService } from '../../domain/interfaces/task-analyzer-service.interface';
import { ISchedulingService } from '../../domain/interfaces/scheduling-service.interface';
import { ConfigService } from '../../../../shared/infrastructure/config/config.service';
import { Task, TaskStatus } from '../../domain/models/task.model';
import { GoogleGenaiAdapter } from '../../../llm/infrastructure/adapters/google-genai.adapter';
import { HistoryService } from '../../../../shared/infrastructure/persistence/history.service';
import { PromptBuilderService } from '../../../../shared/infrastructure/services/prompt-builder.service';
import { HistoryEntry } from '../../../../shared/domain/models/history-entry.model';
import { SendMessageService } from '../../../telegram/application/services/send-message.service';
import { TaskAnalyzerService } from './task-analyzer.service';
import { SchedulingService } from './scheduling.service';
import { VaultService } from '../../../vault/infrastructure/services/vault.service';
import { ProcessMessageService } from '../../../telegram/application/services/process-message.service';
import { LlmResponse } from '../../../llm/application/services/llm-processor.service';

@Injectable()
export class NotificationService implements INotificationService, OnModuleInit {
  private readonly logger = new Logger(NotificationService.name);
  private readonly userLanguage: string = 'ru'; // Default to Russian, could be made configurable
  private activeReminders: Map<string, { taskId: string; scheduledTime: Date }> = new Map();

  constructor(
    readonly taskAnalyzer: TaskAnalyzerService,
    private readonly schedulingService: SchedulingService,
    private readonly configService: ConfigService,
    private readonly llmAdapter: GoogleGenaiAdapter,
    private readonly historyService: HistoryService,
    private readonly promptBuilder: PromptBuilderService,
    @Inject(forwardRef(() => SendMessageService))
    private readonly sendMessageService: SendMessageService,
    private readonly vaultService: VaultService,
    private readonly processMessageService: ProcessMessageService,
  ) {
    // Subscribe to file change events
    this.vaultService.fileEvents.on('fileChanged', async (filename: string) => {
      this.logger.log(`File changed: ${filename}, resetting notifications for this file.`);
      await this.resetAndRescheduleRemindersForFile(filename);
    });
  }

  async onModuleInit() {
    this.logger.log('Notification service initialized');
    // Schedule initial tasks
    await this.resetAndRescheduleAllReminders();
  }

  @Cron(CronExpression.EVERY_DAY_AT_MIDNIGHT)
  async handleDailyReset() {
    this.logger.log('Performing daily notification reset at midnight');
    await this.resetAndRescheduleAllReminders();

    // Send a system notification about the reset
    const userIds = this.configService.getTelegramUserIds();
    for (const userId of userIds) {
      try {
        const numericUserId = parseInt(userId, 10);
        if (!isNaN(numericUserId)) {
          await this.sendMessageService.sendMessage(
            numericUserId,
            '🔄 *System Notification*\nDaily notification reset completed. All reminders for today have been rescheduled.',
            'Markdown',
          );
        }
      } catch (error) {
        this.logger.error(`Error sending daily reset notification to user ${userId}:`, error);
      }
    }
  }

  async resetAndRescheduleAllReminders(): Promise<void> {
    try {
      this.logger.log('Resetting and rescheduling all task reminders');

      // Clear all existing scheduled reminders
      for (const [reminderId] of this.activeReminders) {
        this.schedulingService.unschedule(reminderId);
      }

      // Reset the active reminders map
      this.activeReminders.clear();

      // Get today's tasks and schedule reminders for them
      const todaysTasks = await this.taskAnalyzer.getTodaysTasks();
      this.logger.log(`Found ${todaysTasks.length} tasks for today, scheduling reminders`);

      for (const task of todaysTasks) {
        if (!task.isCompleted()) {
          await this.scheduleRemindersForTask(task);
        }
      }

      this.logger.log(`Successfully rescheduled ${this.activeReminders.size} reminders`);
    } catch (error) {
      this.logger.error(`Error in resetAndRescheduleAllReminders: ${error.message}`, error.stack);
    }
  }

  async sendTaskReminder(task: Task, minutesBefore: number = 15): Promise<boolean> {
    try {
      this.logger.log(
        `Preparing task reminder for "${task.getTitle()}" ${minutesBefore} minutes before`,
      );

      // Get user IDs from config
      const userIds = this.configService.getTelegramUserIds();
      let success = true;

      // Format task date and time for display
      const taskDate = task.getDate();
      const startTime = task.getStartTime();

      let dateTimeStr = '';
      if (taskDate) {
        dateTimeStr = this.formatDate(taskDate);
        if (startTime) {
          dateTimeStr += ` at ${startTime}`;
        }
      }

      // Prepare task data for LLM
      const taskData = {
        title: task.getTitle(),
        description: task.getDescription(),
        date: dateTimeStr,
        priority: task.getPriority(),
        status: task.getStatus(),
        minutesBefore: minutesBefore,
      };

      this.logger.debug(`Task data for LLM: ${JSON.stringify(taskData)}`);

      // Generate personalized notification using LLM
      const llmResponse = await this.generateTaskReminderWithLLM(taskData);

      this.logger.log(`Generated reminder for task "${task.getTitle()}"`);

      // Send message to all configured users
      for (const userId of userIds) {
        try {
          const numericUserId = parseInt(userId, 10);
          if (!isNaN(numericUserId)) {
            this.logger.debug(`Sending task reminder to user ${numericUserId}`);

            // Execute the tool calls from the LLM response
            // Convert numericUserId to string as required by executeToolCalls
            await this.processMessageService.executeToolCalls(llmResponse, userId.toString());
          }
        } catch (error) {
          this.logger.error(`Error sending task reminder to user ${userId}:`, error);
          success = false;
        }
      }

      return success;
    } catch (error) {
      this.logger.error(`Error sending task reminder: ${error.message}`, error.stack);
      return false;
    }
  }

  async sendMorningDigest(userId: number): Promise<boolean> {
    try {
      this.logger.log(`Preparing morning digest for user ${userId}`);

      // Get today's tasks
      const todaysTasks = await this.taskAnalyzer.getTodaysTasks();
      this.logger.debug(`Found ${todaysTasks.length} tasks for today`);

      // Get overdue tasks
      const overdueTasks = await this.taskAnalyzer.getOverdueTasks();
      this.logger.debug(`Found ${overdueTasks.length} overdue tasks`);

      // Prepare data for LLM
      const digestData = {
        date: new Date(),
        todaysTasks: todaysTasks.map((task) => ({
          title: task.getTitle(),
          startTime: task.getStartTime(),
          completed: task.isCompleted(),
          priority: task.getPriority(),
          status: task.getStatus(),
        })),
        overdueTasks: overdueTasks.map((task) => ({
          title: task.getTitle(),
          date: task.getDate() ? this.formatDate(task.getDate()!) : 'No date',
          priority: task.getPriority(),
          status: task.getStatus(),
        })),
      };

      // Generate personalized morning digest using LLM
      const llmResponse = await this.generateMorningDigestWithLLM(digestData);

      this.logger.log(`Generated morning digest for user ${userId}`);

      // Execute the tool calls from the LLM response
      // Convert userId to string as required by executeToolCalls
      await this.processMessageService.executeToolCalls(llmResponse, userId.toString());

      return true;
    } catch (error) {
      this.logger.error(`Error sending morning digest: ${error.message}`, error.stack);
      return false;
    }
  }

  async sendEveningCheckIn(userId: number): Promise<boolean> {
    try {
      this.logger.log(`Preparing evening check-in for user ${userId}`);

      // Get completed tasks for today
      const completedTasksToday = await this.taskAnalyzer.getCompletedTasksToday();
      this.logger.debug(`Found ${completedTasksToday.length} completed tasks for today`);

      // Get uncompleted tasks for today
      const todaysTasks = await this.taskAnalyzer.getTodaysTasks();
      const uncompletedTasksToday = todaysTasks.filter((task) => !task.isCompleted());
      this.logger.debug(`Found ${uncompletedTasksToday.length} uncompleted tasks for today`);

      // Get recent history
      const recentHistory = this.historyService.getHistory().slice(-5);

      // Prepare data for LLM
      const checkInData = {
        date: new Date(),
        completedTasksToday: completedTasksToday.map((task) => ({
          title: task.getTitle(),
          priority: task.getPriority(),
          status: task.getStatus(),
        })),
        uncompletedTasksToday: uncompletedTasksToday.map((task) => ({
          title: task.getTitle(),
          priority: task.getPriority(),
          status: task.getStatus(),
        })),
        recentHistory: this.formatRecentHistory(recentHistory),
      };

      // Generate personalized evening check-in using LLM
      const llmResponse = await this.generateEveningCheckInWithLLM(checkInData);

      this.logger.log(`Generated evening check-in for user ${userId}`);

      // Execute the tool calls from the LLM response
      await this.processMessageService.executeToolCalls(llmResponse, userId.toString());

      return true;
    } catch (error) {
      this.logger.error(`Error sending evening check-in: ${error.message}`, error.stack);
      return false;
    }
  }

  async scheduleRemindersForTask(task: Task): Promise<void> {
    try {
      this.logger.log(`Scheduling reminders for task "${task.getTitle()}"`);

      const taskDate = task.getDate();
      const startTime = task.getStartTime();

      // Skip if task has no date or is already completed
      if (!taskDate || task.isCompleted()) {
        this.logger.debug(
          `Skipping reminder scheduling for task "${task.getTitle()}" - no date or already completed`,
        );
        return;
      }

      // Get reminders configuration
      const reminders = task.getReminders();

      // If task has explicit reminders defined, schedule them
      if (reminders && reminders.length > 0) {
        this.logger.debug(`Task has ${reminders.length} custom reminders defined`);
        for (const reminder of reminders) {
          this.scheduleTaskReminder(task, reminder.minutesBefore);
        }
      } else {
        // Default reminder: 15 minutes before task
        this.logger.debug(`No custom reminders defined, using default 15 minute reminder`);
        this.scheduleTaskReminder(task, 15);
      }
    } catch (error) {
      this.logger.error(`Error scheduling reminders for task: ${error.message}`, error.stack);
    }
  }

  private scheduleTaskReminder(task: Task, minutesBefore: number): void {
    try {
      const taskDate = task.getDate();
      const startTime = task.getStartTime();

      if (!taskDate) {
        return;
      }

      // Create a date object for the reminder time
      const reminderDate = new Date(taskDate);

      // If task has a specific start time, use it
      if (startTime) {
        const [hours, minutes] = startTime.split(':').map(Number);
        reminderDate.setHours(hours, minutes, 0, 0);
      } else {
        // Default to 9:00 AM for all-day tasks
        reminderDate.setHours(9, 0, 0, 0);
      }

      // Subtract the reminder time
      reminderDate.setMinutes(reminderDate.getMinutes() - minutesBefore);

      // Skip if reminder time is in the past
      if (reminderDate <= new Date()) {
        this.logger.debug(
          `Skipping reminder for task "${task.getTitle()}" - reminder time is in the past`,
        );
        return;
      }

      // Format the date and time for the schedule
      const scheduleTime = this.formatTime(reminderDate);
      const scheduleDate = this.formatDate(reminderDate);

      // Create a unique ID for this reminder
      const reminderId = `task_reminder_${this.generateId()}`;

      // Store in active reminders map
      this.activeReminders.set(reminderId, {
        taskId: task.getId(),
        scheduledTime: reminderDate,
      });

      // Schedule the reminder using our scheduling service
      this.schedulingService.addJob(`daily at ${scheduleTime}`, reminderId, () => {
        this.sendTaskReminder(task, minutesBefore);
        // Remove from active reminders after it's triggered
        this.activeReminders.delete(reminderId);
      });

      this.logger.log(
        `Scheduled reminder for "${task.getTitle()}" at ${scheduleDate} ${scheduleTime} (${minutesBefore} minutes before)`,
      );
    } catch (error) {
      this.logger.error(`Error scheduling task reminder: ${error.message}`, error.stack);
    }
  }

  // Helper methods to replace date-fns
  private formatDate(date: Date): string {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  }

  private formatTime(date: Date): string {
    return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
  }

  private formatShortDate(date: Date): string {
    const monthNames = [
      'Jan',
      'Feb',
      'Mar',
      'Apr',
      'May',
      'Jun',
      'Jul',
      'Aug',
      'Sep',
      'Oct',
      'Nov',
      'Dec',
    ];
    return `${monthNames[date.getMonth()]} ${date.getDate()}`;
  }

  // Simple UUID generator to replace uuid
  private generateId(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // LLM-based notification generators
  private async generateTaskReminderWithLLM(taskData: any): Promise<LlmResponse> {
    try {
      // Get recent conversation history
      const history = this.historyService.getHistory();
      const formattedHistory = this.formatRecentHistory(history);

      const systemInstruction = `You are an AI assistant tasked with creating personalized task reminders.

TASK:
Create a concise, friendly reminder notification for an upcoming task.
Include emoji, format with Markdown, and maintain a helpful tone.
Include the task title, time, description (if available), priority, and status.
Keep the reminder under 200 words and make it motivational.

IMPORTANT: Use ${this.userLanguage} language for your response.

Recent conversation history for context (use this to personalize the message):
--- CONVERSATION HISTORY START ---
${formattedHistory}
--- CONVERSATION HISTORY END ---

RESPONSE FORMAT:
Your response MUST be valid and properly formatted for the reply tool.
Format your response for the tool call with the following structure:
[
  {
    "tool": "reply",
    "params": {
      "message": "Your well-formatted reminder message here"
    }
  }
]

Do not include any text outside the JSON structure. Ensure your message is concise, friendly, and motivational.
`;

      this.logger.debug('Calling LLM to generate task reminder');
      const response = await this.llmAdapter.generateContent(
        [{ text: JSON.stringify(taskData) }],
        systemInstruction,
        'text/plain',
      );

      if (!response || !response.text) {
        this.logger.warn('LLM did not return a valid response for task reminder');
        // Fallback to a simple reminder format
        return {
          toolCalls: [
            {
              tool: 'reply',
              params: {
                message: this.createFallbackTaskReminder(taskData),
              },
            },
          ],
          error: 'LLM did not return a valid response for task reminder',
        };
      }

      // Add the LLM response to history
      const assistantEntry: HistoryEntry = {
        role: 'assistant',
        content: response.text,
        timestamp: new Date(),
      };
      this.historyService.appendEntry(assistantEntry);

      // Try to parse the response as JSON tool call
      try {
        const parsedResponse = JSON.parse(response.text);
        if (
          Array.isArray(parsedResponse) &&
          parsedResponse.length > 0 &&
          parsedResponse[0].tool === 'reply' &&
          parsedResponse[0].params?.message
        ) {
          return {
            toolCalls: parsedResponse,
          };
        }
      } catch (e) {
        this.logger.warn(`Failed to parse LLM response as JSON: ${e.message}`);
      }

      // If parsing failed or incorrect format, convert text to toolCalls
      return {
        toolCalls: [
          {
            tool: 'reply',
            params: {
              message: response.text,
            },
          },
        ],
      };
    } catch (error) {
      this.logger.error(`Error generating task reminder with LLM: ${error.message}`, error.stack);
      // Fallback to a simple reminder format
      return {
        toolCalls: [
          {
            tool: 'reply',
            params: {
              message: this.createFallbackTaskReminder(taskData),
            },
          },
        ],
        error: error.message || 'Error generating task reminder',
      };
    }
  }

  private createFallbackTaskReminder(taskData: any): string {
    // Create a simple fallback reminder in Russian
    if (this.userLanguage === 'ru') {
      return `🔔 *Напоминание:* ${taskData.title}\n\n${taskData.date ? `⏰ Запланировано на ${taskData.date}\n\n` : ''}${taskData.description ? `📝 ${taskData.description}\n\n` : ''}Приоритет: ${this.getPriorityText(taskData.priority)}\nСтатус: ${taskData.status}`;
    }

    // English fallback
    return `🔔 *Reminder:* ${taskData.title}\n\n${taskData.date ? `⏰ Scheduled for ${taskData.date}\n\n` : ''}${taskData.description ? `📝 ${taskData.description}\n\n` : ''}Priority: ${this.getPriorityText(taskData.priority)}\nStatus: ${taskData.status}`;
  }

  private async generateMorningDigestWithLLM(digestData: any): Promise<LlmResponse> {
    try {
      // Get recent conversation history
      const history = this.historyService.getHistory();
      const formattedHistory = this.formatRecentHistory(history);

      const systemInstruction = `You are an AI assistant tasked with creating personalized morning digests.

TASK:
Create a concise, friendly morning digest that summarizes the day's tasks and any overdue items.
Include emoji, format with Markdown, and maintain a motivational tone.
Include the date, list of today's tasks with their status, and any overdue tasks.
End with a brief motivational message. Keep the digest under 300 words.

IMPORTANT: Use ${this.userLanguage} language for your response.

Recent conversation history for context:
--- CONVERSATION HISTORY START ---
${formattedHistory}
--- CONVERSATION HISTORY END ---

RESPONSE FORMAT:
Your response MUST be valid and properly formatted for the reply tool.
Format your response for the tool call with the following structure:
[
  {
    "tool": "reply",
    "params": {
      "message": "Your well-formatted morning digest here"
    }
  }
]

Do not include any text outside the JSON structure. Ensure your message is concise, friendly, and motivational.
`;

      this.logger.debug('Calling LLM to generate morning digest');
      const response = await this.llmAdapter.generateContent(
        [{ text: JSON.stringify(digestData) }],
        systemInstruction,
        'text/plain',
      );

      if (!response || !response.text) {
        this.logger.warn('LLM did not return a valid response for morning digest');
        // Create a fallback digest
        return {
          toolCalls: [
            {
              tool: 'reply',
              params: {
                message: this.createFallbackMorningDigest(digestData),
              },
            },
          ],
          error: 'LLM did not return a valid response for morning digest',
        };
      }

      // Add the LLM response to history
      const assistantEntry: HistoryEntry = {
        role: 'assistant',
        content: response.text,
        timestamp: new Date(),
      };
      this.historyService.appendEntry(assistantEntry);

      // Try to parse the response as JSON tool call
      try {
        const parsedResponse = JSON.parse(response.text);
        if (
          Array.isArray(parsedResponse) &&
          parsedResponse.length > 0 &&
          parsedResponse[0].tool === 'reply' &&
          parsedResponse[0].params?.message
        ) {
          return {
            toolCalls: parsedResponse,
          };
        }
      } catch (e) {
        this.logger.warn(`Failed to parse LLM response as JSON: ${e.message}`);
      }

      // If parsing failed or incorrect format, convert text to toolCalls
      return {
        toolCalls: [
          {
            tool: 'reply',
            params: {
              message: response.text,
            },
          },
        ],
      };
    } catch (error) {
      this.logger.error(`Error generating morning digest with LLM: ${error.message}`, error.stack);
      // Create a fallback digest
      return {
        toolCalls: [
          {
            tool: 'reply',
            params: {
              message: this.createFallbackMorningDigest(digestData),
            },
          },
        ],
        error: error.message || 'Error generating morning digest',
      };
    }
  }

  private createFallbackMorningDigest(digestData: any): string {
    const today = new Date();
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const monthNames = [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];

    // Russian day and month names
    const ruDayNames = [
      'Воскресенье',
      'Понедельник',
      'Вторник',
      'Среда',
      'Четверг',
      'Пятница',
      'Суббота',
    ];
    const ruMonthNames = [
      'Января',
      'Февраля',
      'Марта',
      'Апреля',
      'Мая',
      'Июня',
      'Июля',
      'Августа',
      'Сентября',
      'Октября',
      'Ноября',
      'Декабря',
    ];

    let message = '';
    if (this.userLanguage === 'ru') {
      message = `🌞 *Доброе утро!* Вот ваши задачи на ${ruDayNames[today.getDay()]}, ${today.getDate()} ${ruMonthNames[today.getMonth()]}:\n\n`;

      // Add today's tasks section
      message += `*Задачи на сегодня (${digestData.todaysTasks.length}):*\n`;
      if (digestData.todaysTasks.length > 0) {
        digestData.todaysTasks.forEach((task: any, index: number) => {
          const startTime = task.startTime ? ` в ${task.startTime}` : '';
          message += `${index + 1}. ${task.completed ? '✅' : '⬜'} ${task.title}${startTime}\n`;
        });
      } else {
        message += 'На сегодня нет запланированных задач.\n';
      }

      // Add overdue tasks section if any
      if (digestData.overdueTasks.length > 0) {
        message += `\n*Просроченные задачи (${digestData.overdueTasks.length}):*\n`;
        digestData.overdueTasks.forEach((task: any, index: number) => {
          message += `${index + 1}. ⚠️ ${task.title} (срок: ${task.date})\n`;
        });
      }

      // Add motivational message
      message += '\nЖелаю продуктивного дня! 💪';
    } else {
      // English fallback
      message = `🌞 *Good morning!* Here's your task digest for ${dayNames[today.getDay()]}, ${monthNames[today.getMonth()]} ${today.getDate()}:\n\n`;

      // Add today's tasks section
      message += `*Today's Tasks (${digestData.todaysTasks.length}):*\n`;
      if (digestData.todaysTasks.length > 0) {
        digestData.todaysTasks.forEach((task: any, index: number) => {
          const startTime = task.startTime ? ` at ${task.startTime}` : '';
          message += `${index + 1}. ${task.completed ? '✅' : '⬜'} ${task.title}${startTime}\n`;
        });
      } else {
        message += 'No tasks scheduled for today.\n';
      }

      // Add overdue tasks section if any
      if (digestData.overdueTasks.length > 0) {
        message += `\n*Overdue Tasks (${digestData.overdueTasks.length}):*\n`;
        digestData.overdueTasks.forEach((task: any, index: number) => {
          message += `${index + 1}. ⚠️ ${task.title} (due: ${task.date})\n`;
        });
      }

      // Add motivational message
      message += '\nHave a productive day! 💪';
    }

    return message;
  }

  private formatRecentHistory(history: HistoryEntry[]): string {
    if (!history || history.length === 0) {
      return 'No recent conversation history.';
    }

    // Limit to last 5 messages to avoid context length issues
    const recentHistory = history.slice(-5);

    return recentHistory
      .map((entry) => {
        const timestamp = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '';
        const role = entry.role === 'user' ? 'User' : 'Assistant';

        // For assistant entries that might contain JSON tool calls, format them nicely
        let content = entry.content;
        if (
          role === 'Assistant' &&
          content.trim().startsWith('[') &&
          content.trim().endsWith(']')
        ) {
          try {
            const toolCalls = JSON.parse(content);
            if (Array.isArray(toolCalls)) {
              // Find reply tool calls to show in history
              const replyTools = toolCalls.filter((tool) => tool.tool === 'reply');
              if (replyTools.length > 0) {
                content = replyTools.map((tool) => tool.params?.message || '').join('\n');
              } else {
                // If no reply tools, summarize the actions
                content = `[Performed ${toolCalls.length} operations: ${toolCalls.map((t) => t.tool).join(', ')}]`;
              }
            }
          } catch (e) {
            // If parsing fails, use the original content
          }
        }

        return `[${timestamp}] ${role}: ${content.substring(0, 400)}${content.length > 400 ? '...' : ''}`;
      })
      .join('\n\n');
  }

  private async generateEveningCheckInWithLLM(checkInData: any): Promise<LlmResponse> {
    try {
      // Get recent conversation history
      const history = this.historyService.getHistory();
      const formattedHistory = this.formatRecentHistory(history);

      const systemInstruction = `You are an AI assistant tasked with creating personalized evening check-in summaries.

TASK:
Create a concise, friendly evening summary that reviews completed tasks, pending items, and postponed tasks.
Include emoji, format with Markdown, and maintain a supportive tone.
Include lists of completed tasks, pending tasks, and postponed tasks.
End with a reflection prompt. Keep the check-in under 300 words.

IMPORTANT: Use ${this.userLanguage} language for your response.

Recent conversation history for context:
--- CONVERSATION HISTORY START ---
${formattedHistory}
--- CONVERSATION HISTORY END ---

RESPONSE FORMAT:
Your response MUST be valid and properly formatted for the reply tool.
Format your response for the tool call with the following structure:
[
  {
    "tool": "reply",
    "params": {
      "message": "Your well-formatted evening check-in here"
    }
  }
]

Do not include any text outside the JSON structure. Ensure your message is concise, friendly, and supportive.
`;

      this.logger.debug('Calling LLM to generate evening check-in');
      const response = await this.llmAdapter.generateContent(
        [{ text: JSON.stringify(checkInData) }],
        systemInstruction,
        'text/plain',
      );

      if (!response || !response.text) {
        this.logger.warn('LLM did not return a valid response for evening check-in');
        // Create a fallback check-in
        return {
          toolCalls: [
            {
              tool: 'reply',
              params: {
                message: this.createFallbackEveningCheckIn(checkInData),
              },
            },
          ],
          error: 'LLM did not return a valid response for evening check-in',
        };
      }

      // Add the LLM response to history
      const assistantEntry: HistoryEntry = {
        role: 'assistant',
        content: response.text,
        timestamp: new Date(),
      };
      this.historyService.appendEntry(assistantEntry);

      // Try to parse the response as JSON tool call
      try {
        const parsedResponse = JSON.parse(response.text);
        if (
          Array.isArray(parsedResponse) &&
          parsedResponse.length > 0 &&
          parsedResponse[0].tool === 'reply' &&
          parsedResponse[0].params?.message
        ) {
          return {
            toolCalls: parsedResponse,
          };
        }
      } catch (e) {
        this.logger.warn(`Failed to parse LLM response as JSON: ${e.message}`);
      }

      // If parsing failed or incorrect format, convert text to toolCalls
      return {
        toolCalls: [
          {
            tool: 'reply',
            params: {
              message: response.text,
            },
          },
        ],
      };
    } catch (error) {
      this.logger.error(
        `Error generating evening check-in with LLM: ${error.message}`,
        error.stack,
      );
      // Create a fallback check-in
      return {
        toolCalls: [
          {
            tool: 'reply',
            params: {
              message: this.createFallbackEveningCheckIn(checkInData),
            },
          },
        ],
        error: error.message || 'Error generating evening check-in',
      };
    }
  }

  private createFallbackEveningCheckIn(checkInData: any): string {
    let message = '';

    if (this.userLanguage === 'ru') {
      message = `🌙 *Вечерняя проверка*\n\n`;

      // Add completed tasks section
      message += `*Выполнено сегодня (${checkInData.completedTasksToday.length}):*\n`;
      if (checkInData.completedTasksToday.length > 0) {
        checkInData.completedTasksToday.forEach((task: any, index: number) => {
          message += `${index + 1}. ✅ ${task.title}\n`;
        });
      } else {
        message += 'Сегодня не выполнено ни одной задачи.\n';
      }

      // Add uncompleted tasks section
      message += `\n*Остаются на выполнении (${checkInData.uncompletedTasksToday.length}):*\n`;
      if (checkInData.uncompletedTasksToday.length > 0) {
        checkInData.uncompletedTasksToday.forEach((task: any, index: number) => {
          message += `${index + 1}. ⬜ ${task.title}\n`;
        });
      } else {
        message += 'Все задачи выполнены! Отличная работа!\n';
      }

      // Add reflection prompt
      message +=
        '\n*Ежедневная рефлексия:*\nКак прошел ваш день? Есть ли достижения или испытания, которые вы хотели бы отметить?';
    } else {
      // English version
      message = `🌙 *Evening Check-In*\n\n`;

      // Add completed tasks section
      message += `*Completed Today (${checkInData.completedTasksToday.length}):*\n`;
      if (checkInData.completedTasksToday.length > 0) {
        checkInData.completedTasksToday.forEach((task: any, index: number) => {
          message += `${index + 1}. ✅ ${task.title}\n`;
        });
      } else {
        message += 'No tasks completed today.\n';
      }

      // Add uncompleted tasks section
      message += `\n*Still Pending (${checkInData.uncompletedTasksToday.length}):*\n`;
      if (checkInData.uncompletedTasksToday.length > 0) {
        checkInData.uncompletedTasksToday.forEach((task: any, index: number) => {
          message += `${index + 1}. ⬜ ${task.title}\n`;
        });
      } else {
        message += 'All tasks completed! Great job!\n';
      }

      // Add reflection prompt
      message +=
        '\n*Daily Reflection:*\nHow was your day? Any achievements or challenges you want to note?';
    }

    return message;
  }

  private getPriorityText(priority?: number): string {
    if (!priority) return 'Не установлен';

    if (this.userLanguage === 'ru') {
      switch (priority) {
        case 1:
          return 'Наивысший';
        case 2:
          return 'Высокий';
        case 3:
          return 'Средний';
        case 4:
          return 'Низкий';
        case 5:
          return 'Наименьший';
        default:
          return 'Не установлен';
      }
    }

    // English fallback
    switch (priority) {
      case 1:
        return 'Highest';
      case 2:
        return 'High';
      case 3:
        return 'Medium';
      case 4:
        return 'Low';
      case 5:
        return 'Lowest';
      default:
        return 'Not set';
    }
  }

  /**
   * Reset and reschedule reminders for a specific file (task)
   */
  async resetAndRescheduleRemindersForFile(filename: string): Promise<void> {
    try {
      this.logger.log(`Resetting and rescheduling reminders for file: ${filename}`);
      // Remove any active reminders for this file
      for (const [reminderId, reminder] of this.activeReminders) {
        if (reminder.taskId && reminder.taskId.includes(filename)) {
          this.schedulingService.unschedule(reminderId);
          this.activeReminders.delete(reminderId);
        }
      }
      // Find the task for this file and reschedule reminders
      const todaysTasks = await this.taskAnalyzer.getTodaysTasks();

      for (const task of todaysTasks) {
        if (!task.isCompleted()) {
          await this.scheduleRemindersForTask(task);
        }
      }
      this.logger.log(`Rescheduled reminders for file: ${filename}`);
    } catch (error) {
      this.logger.error(
        `Error in resetAndRescheduleRemindersForFile: ${error.message}`,
        error.stack,
      );
    }
  }
}
