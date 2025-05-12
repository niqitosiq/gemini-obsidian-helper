import { Injectable, Logger, Inject } from '@nestjs/common';
import { IToolHandler } from '../../domain/interfaces/tool-handler.interface';
import {
  CreateFileToolHandler,
  DeleteFileToolHandler,
  FinishToolHandler,
  ModifyFileToolHandler,
  ReplyToolHandler,
} from '../../infrastructure/services/file-tools.service';

/**
 * Interface for tool definition
 */
interface ToolDefinition {
  name: string;
  description: string;
  required: string[];
  parameters: {
    properties: Record<string, any>;
  };
}

/**
 * Service for registering and managing tools that can be used by the LLM
 */
@Injectable()
export class ToolsRegistryService {
  private readonly logger = new Logger(ToolsRegistryService.name);
  private readonly tools: Map<string, IToolHandler> = new Map();
  private toolDefinitions: ToolDefinition[] = [];

  constructor(
    private readonly createFileTool: CreateFileToolHandler,
    private readonly modifyFileTool: ModifyFileToolHandler,
    private readonly deleteFileTool: DeleteFileToolHandler,
    private readonly replyTool: ReplyToolHandler,
    private readonly finishTool: FinishToolHandler,
  ) {
    this.registerBuiltInTools();
    this.initializeToolDefinitions();
  }

  private registerBuiltInTools(): void {
    this.registerTool('create_file', this.createFileTool);
    this.registerTool('modify_file', this.modifyFileTool);
    this.registerTool('delete_file', this.deleteFileTool);
    this.registerTool('reply', this.replyTool);
    this.registerTool('finish', this.finishTool);
  }

  /**
   * Initialize the tool definitions
   */
  private initializeToolDefinitions(): void {
    // Define the available tools
    this.toolDefinitions = [
      {
        name: 'create_file',
        description: 'Creates a new file with the specified content',
        required: ['file_path', 'content'],
        parameters: {
          properties: {
            file_path: {
              type: 'string',
              description: 'Path to the file to create',
            },
            content: {
              type: 'string',
              description: 'Content to write to the file',
            },
          },
        },
      },
      {
        name: 'modify_file',
        description: 'Modifies an existing file with new content',
        required: ['file_path', 'content'],
        parameters: {
          properties: {
            file_path: {
              type: 'string',
              description: 'Path to the file to modify',
            },
            content: {
              type: 'string',
              description: 'New content for the file',
            },
          },
        },
      },
      {
        name: 'delete_file',
        description: 'Deletes an existing file',
        required: ['file_path'],
        parameters: {
          properties: {
            file_path: {
              type: 'string',
              description: 'Path to the file to delete',
            },
          },
        },
      },
      {
        name: 'reply',
        description: 'Sends a message to the user',
        required: ['message'],
        parameters: {
          properties: {
            message: {
              type: 'string',
              description: 'Message to send to the user',
            },
          },
        },
      },
      {
        name: 'finish',
        description: 'Ends the conversation',
        required: [],
        parameters: {
          properties: {},
        },
      },
    ];
  }

  /**
   * Register a new tool
   *
   * @param name - The name of the tool
   * @param handler - The function that implements the tool
   */
  registerTool(name: string, handler: IToolHandler): void {
    this.tools.set(name, handler);
    this.logger.log(`Registered tool: ${name}`);
  }

  /**
   * Check if a tool handler exists for a given tool name
   *
   * @param name - The name of the tool to check
   * @returns True if the tool handler exists, false otherwise
   */
  hasToolHandler(name: string): boolean {
    return this.tools.has(name);
  }

  /**
   * Execute a tool by name
   *
   * @param name - The name of the tool to execute
   * @param params - The parameters to pass to the tool
   * @returns The result of the tool execution
   */
  async executeTool(name: string, params: Record<string, any>): Promise<Record<string, any>> {
    const handler = this.tools.get(name);
    if (!handler) {
      return {
        status: 'error',
        message: `Tool '${name}' not found`,
      };
    }

    try {
      return await handler.execute(params);
    } catch (error) {
      return {
        status: 'error',
        message: `Error executing tool '${name}': ${error.message || error}`,
      };
    }
  }

  /**
   * Get the list of available tool names
   *
   * @returns Array of tool names
   */
  getAvailableTools(): string[] {
    return Array.from(this.tools.keys());
  }

  /**
   * Get the tool definitions
   *
   * @returns Array of tool definitions
   */
  getToolDefinitions(): ToolDefinition[] {
    return this.toolDefinitions;
  }
}
