import { Injectable, Logger, Inject, Optional } from '@nestjs/common';
import { IPromptBuilderService } from '../../domain/interfaces/prompt-builder-service.interface';
import { HistoryEntry } from '../../domain/models/history-entry.model';
import { ToolsRegistryService } from '../../../modules/tools/application/services/tools-registry.service';

@Injectable()
export class PromptBuilderService implements IPromptBuilderService {
  private readonly logger = new Logger(PromptBuilderService.name);
  private toolDefsCache: any[] = [];

  constructor(@Optional() private readonly toolsRegistry?: ToolsRegistryService) {
    this.logger.debug('PromptBuilderService initialized.');
    try {
      // Cache tool definitions if toolsRegistry is available
      if (this.toolsRegistry) {
        this.toolDefsCache = this.toolsRegistry.getToolDefinitions();
        this.logger.debug(`Cached ${this.toolDefsCache.length} tool definitions.`);
      } else {
        this.logger.warn('ToolsRegistryService not available. Tool definitions will be empty.');
        this.toolDefsCache = [];
      }
    } catch (e) {
      this.logger.error(`Failed to get or cache tool definitions: ${e}`, e.stack);
      this.toolDefsCache = []; // Use empty array in case of error
    }
  }

  private formatToolDescriptions(): string {
    if (!this.toolDefsCache || this.toolDefsCache.length === 0) {
      if (this.toolsRegistry) {
        this.logger.warn(
          'Tool definitions cache is empty. Attempting to load tool definitions now.',
        );
        try {
          // Try to get tool definitions now in case they're available
          const toolDefs = this.toolsRegistry.getToolDefinitions();
          if (toolDefs.length > 0) {
            this.toolDefsCache = toolDefs;
          }
        } catch (e) {
          this.logger.error(`Failed to get tool definitions: ${e.message}`);
        }
      }

      // If still no tool definitions, return a message
      if (!this.toolDefsCache || this.toolDefsCache.length === 0) {
        return 'No tools available or failed to load definitions.';
      }
    }

    const descriptionLines: string[] = [];

    for (const tool of this.toolDefsCache) {
      const name = tool.name || 'unnamed_tool';
      const description = tool.description || 'No description.';
      descriptionLines.push(`- ${name}: ${description}`);

      const paramDetails: string[] = [];
      const requiredParams = tool.required || [];
      const parameters = tool.parameters;

      // Check if parameters is an object and not empty
      if (parameters && typeof parameters === 'object' && Object.keys(parameters).length > 0) {
        for (const key of Object.keys(parameters.properties || {})) {
          const status = requiredParams.includes(key) ? 'required' : 'optional';
          paramDetails.push(`${key} (${status})`);
        }
      }

      if (paramDetails.length > 0) {
        // Use join for proper formatting of parameter list
        descriptionLines.push(`  Parameters: { ${paramDetails.join(', ')} }`);
      } else {
        descriptionLines.push('  Parameters: None');
      }
    }

    // Use '\n' for proper line breaks in the final prompt
    return descriptionLines.join('\n');
  }

  private getTaskTemplate(): string {
    // Task template in Obsidian format
    return `---
title: [Task Title]
allDay: true
date: [YYYY-MM-DD or leave empty]
completed: false
priority: [1-5 or leave empty]
status: [e.g., todo, waiting, in progress - default to todo if unsure]
type: single
depends_on: [] # Optional: Add links like - "[[Other Note Title]]" if mentioned
blocks: [] # Optional: Add links like - "[[Other Note Title]]" if mentioned
startTime: [HH:MM or leave empty]
endTime: [HH:MM or leave empty]
endDate: [YYYY-MM-DD or leave empty]
duration: [HH:MM or leave empty]
---

## 📝 Описание
[Detailed description of the task provided by the user]`;
  }

  private getTaskExamples(): string {
    return `TASK CREATION EXAMPLES:

Example 1: User asks "Create a task to buy groceries"
[
  {
    "tool": "create_file",
    "data": {
      "file_path": "03 - Tasks/2023-05-12 Buy groceries.md",
      "content": "---\\ntitle: Buy groceries\\nallDay: true\\ndate: 2023-05-12\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: []\\nblocks: []\\n---\\n\\n## 📝 Описание\\nBuy groceries for the week"
    }
  },
  {
    "tool": "reply",
    "data": {
      "message": "✅ I've created a task 'Buy groceries' scheduled for today."
    }
  }
]

Example 2: User asks "Add a task to call mom tomorrow"
[
  {
    "tool": "create_file",
    "data": {
      "file_path": "03 - Tasks/2023-05-13 Call mom.md",
      "content": "---\\ntitle: Call mom\\nallDay: true\\ndate: 2023-05-13\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: []\\nblocks: []\\n---\\n\\n## 📝 Описание\\nCall mom to check how she's doing"
    }
  },
  {
    "tool": "reply",
    "data": {
      "message": "✅ I've created a task 'Call mom' scheduled for tomorrow (May 13, 2023)."
    }
  }
]`;
  }

  private getToolCallExample(): string {
    // Example JSON for tool calls
    return `\`\`\`json
[
  {
    "tool": "create_file",
    "data": {
      "file_path": "03 - Tasks/2025-04-25 Task A.md",
      "content": "---\\ntitle: Task A\\nallDay: true\\ndate: 2025-04-25\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: []\\nblocks: []\\n---\\n\\n## 📝 Описание\\nDescription for Task A"
    }
  },
  {
    "tool": "create_file",
    "data": {
      "file_path": "03 - Tasks/2025-04-26 Task B.md",
      "content": "---\\ntitle: Task B\\nallDay: true\\ndate: 2025-04-26\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: []\\nblocks: []\\n---\\n\\n## 📝 Описание\\nDescription for Task B"
    }
  },
  {
    "tool": "modify_file",
    "data": {
      "file_path": "03 - Tasks/2025-04-25 Task A.md",
      "content": "---\\ntitle: Task A\\nallDay: true\\ndate: 2025-04-25\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: []\\nblocks: [\\\"[[2025-04-26 Task B]]\\\"]\\n---\\n\\n## 📝 Описание\\nDescription for Task A"
    }
  },
  {
    "tool": "modify_file",
    "data": {
      "file_path": "03 - Tasks/2025-04-26 Task B.md",
      "content": "---\\ntitle: Task B\\nallDay: true\\ndate: 2025-04-26\\ncompleted: false\\nstatus: todo\\ntype: single\\ndepends_on: [\\\"[[2025-04-25 Task A]]\\\"]\\nblocks: []\\n---\\n\\n## 📝 Описание\\nDescription for Task B"
    }
  },
  {
    "tool": "reply",
    "data": {
      "message": "✅ OK, I've created Task A and Task B and linked them."
    }
  }
]
\`\`\``;
  }

  private getInstructions(): string {
    // Detailed instructions for LLM
    return `- CRITICAL: Your response MUST ALWAYS be a valid JSON array of tool calls, NEVER plain text.
- Analyze the user's request carefully. Identify all distinct actions required (e.g., create multiple files, link them, reply).
- Determine the correct tool and parameters for each action based on the 'Available Tools' list.
- **Chain Commands:** Combine ALL necessary tool calls for a single user request into ONE JSON array response. If a user asks to create two tasks and link them, your response array MUST contain the \`create_file\` calls for both tasks AND the \`modify_file\` calls to link them, plus a final \`reply\` if appropriate. Do NOT perform only part of the request and wait for further instructions.
- **Important:** Ensure all strings within the JSON \`data\` object are properly escaped, especially quotes (\\\\\\\") and newlines (\\\\n) within the \`content\` for file operations or \`message\` for replies.
- **Task Storage Location:** ALWAYS create task files in the "03 - Tasks" folder. When a user asks to "add a task", "create a task", "make a task", or similar, ALWAYS use the file path "03 - Tasks/YYYY-MM-DD Task Name.md". Never create tasks in the root directory or any other folder.
- **File Naming Convention:** When creating task files requested by the user, always use the format \`YYYY-MM-DD Task Name.md\` for the file name, using the date the task is scheduled for. Example: \`2025-04-25 Дизайн Макетов.md\`. Use today's date if no date is specified.
- **Default Date:** If the date for a task is not specified by the user, always use today's date (provided above) as the default both in the filename and in the frontmatter's \`date\` field.
- **Task Content:** When using \`create_file\` for a task, ensure the \`content\` parameter includes both the YAML frontmatter (using the template above) and the description section.
- **Task Linking:** When a user requests linking (e.g., "task A depends on B", "B blocks A", "свяжи А и Б"), use the \`modify_file\` tool for **both** tasks within the *same response array* as the creation calls (if applicable):
    - For "A depends on B": In Task A's file content, add/append \`depends_on: ["[[Task B]]"]\` to the frontmatter. In Task B's file content, add/append \`blocks: ["[[Task A]]"]\` to the frontmatter.
    - Ensure you use the correct Obsidian link format \`[["File Name"]]\` without the \`.md\` extension within the YAML list. Modify the *entire* content string passed to \`modify_file\`.
- **Task Completion:** If the user asks to "выполни" or "complete" a task, use the \`modify_file\` tool. Provide the *entire new content* for the file, changing only the \`completed: false\` line to \`completed: true\` in the frontmatter.
- **Task Planning/Estimation:** When asked for planning or time estimation:
    - Analyze the task. Provide realistic time estimates in your \`reply\`.
    - If creating/modifying the task file, update the \`startTime\`, \`endTime\`, or \`duration\` fields in the frontmatter based on the estimate or user input (e.g., "это займет 2 часа").
    - Schedule tasks logically, avoiding overlap if possible, considering existing tasks (if context allows).
- **File Paths:** Always use relative paths for \`file_path\` and \`folder_path\` tool parameters (e.g., \`03 - Tasks/My Task.md\`, \`01 - Projects/New Project\`). Do not use absolute paths.
- **Daily Notes/Non-Task Content:** If the user provides general information, observations, or asks to "запиши", create or append to a daily note file.
    - Use the \`create_file\` or \`modify_file\` tool.
    - The filename should be \`YYYY-MM-DD.md\` (using today's date) in the \`02 - Daily Notes\` folder.
- **Use \`finish\` Tool:** Only use the \`finish\` tool if the user explicitly indicates the end of the conversation (e.g., "спасибо, это все", "ok, done").
- **NEVER respond with plain text** - always use the JSON array format with tool calls.
- **JSON FORMAT IS REQUIRED:** Your entire response MUST be a valid, parseable JSON array. No text before or after the JSON array is allowed.
- **ALWAYS INCLUDE A REPLY TOOL:** Every response should include at least one "reply" tool call to communicate with the user.
- **AVOID COMMON MISTAKES:**
  - Do not include markdown code block markers (\`\`\`) around your JSON
  - Do not include explanations outside the JSON array
  - Do not start with phrases like "Here's the JSON:" or "I'll help you with that"
  - Ensure all quotes, brackets, and braces are properly balanced
  - Escape all special characters in strings properly
  - ALWAYS put task files in the "03 - Tasks" folder, never in the root directory`;
  }

  public buildSystemPrompt(history: HistoryEntry[], vaultContext?: string): string {
    // Get prompt components
    const toolDescriptions = this.formatToolDescriptions();
    const taskTemplate = this.getTaskTemplate();
    const taskExamples = this.getTaskExamples();
    const toolExample = this.getToolCallExample();
    const instructions = this.getInstructions();

    // Get current date and time
    const currentDatetimeStr = new Date().toLocaleString();

    // Form prompt lines
    const promptLines = [
      'You are an AI assistant designed to manage files within an Obsidian vault.',
      'Your primary functions are file and folder manipulation (create, delete, modify) based on user requests, including managing tasks and daily notes.',
      `\nThe current date and time is: ${currentDatetimeStr}`,
    ];

    // Format conversation history if available
    if (history && history.length > 0) {
      const formattedHistory = this.formatConversationHistory(history);
      if (formattedHistory) {
        promptLines.push(
          '\nHere is your conversation history with the user:',
          '--- CONVERSATION HISTORY START ---',
          formattedHistory,
          '--- CONVERSATION HISTORY END ---\n',
        );
      }
    }

    // Add vault context if available
    if (vaultContext) {
      promptLines.push(
        '\nCurrent content of relevant files from the Obsidian vault is provided below. Refer to this content when needed.',
      );
      promptLines.push('--- VAULT CONTEXT START ---');
      promptLines.push(vaultContext);
      promptLines.push('--- VAULT CONTEXT END ---\n');
    } else {
      promptLines.push('\nNo specific vault file context provided for this request.');
    }

    // Add remaining parts
    promptLines.push(
      'Available Tools:',
      toolDescriptions,
      '\nTask Creation Template:',
      'When asked to create a task, use the `create_file` tool with content formatted like this template:',
      taskTemplate,
      '\nIMPORTANT: ALWAYS create task files in the "03 - Tasks" folder, never in the root directory.',
      taskExamples,
      '\nOutput Format for Tool Calls:',
      "CRITICAL: Your response MUST ALWAYS be a JSON array containing one or more tool call objects. Each object must have 'tool' (string) and 'data' (object) keys. NEVER respond with plain text.",
      '\nExample Of Tool Call Response:',
      toolExample,
      '\nInstructions:',
      instructions,
      '\nFORMATTING REQUIREMENT:',
      'Your entire response must be ONLY a valid JSON array. No text before or after the JSON array. No markdown code block markers. Just the raw JSON array.',
      '\nREMINDER: When a user asks to add/create a task, ALWAYS create the file in the "03 - Tasks" folder with the format "03 - Tasks/YYYY-MM-DD Task Name.md".',
    );

    // Build final prompt
    const systemPrompt = promptLines.join('\n\n'); // Use double line breaks for better readability
    this.logger.debug(`Built system prompt. Final Length: ${systemPrompt.length}`);
    return systemPrompt;
  }

  /**
   * Format conversation history into a readable string
   *
   * @param history - Array of history entries
   * @returns Formatted conversation history string
   */
  private formatConversationHistory(history: HistoryEntry[]): string {
    if (!history || history.length === 0) {
      return '';
    }

    // Limit history to last 10 messages to avoid context length issues
    const recentHistory = history.slice(-10);

    return recentHistory
      .map((entry) => {
        const timestamp = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '';
        const role = entry.role === 'user' ? 'User' : 'Assistant';

        // For assistant entries that contain JSON tool calls, format them nicely
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

        return `[${timestamp}] ${role}: ${content}`;
      })
      .join('\n\n');
  }
}
