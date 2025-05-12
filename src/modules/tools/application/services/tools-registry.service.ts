import { Injectable, Inject } from '@nestjs/common';
import { IToolHandler } from '../../domain/interfaces/tool-handler.interface';

@Injectable()
export class ToolsRegistryService {
  private readonly tools: Map<string, IToolHandler> = new Map();

  constructor(
    @Inject('CreateFileTool') private readonly createFileTool: IToolHandler,
    @Inject('ModifyFileTool') private readonly modifyFileTool: IToolHandler,
    @Inject('DeleteFileTool') private readonly deleteFileTool: IToolHandler,
  ) {
    this.registerBuiltInTools();
  }

  private registerBuiltInTools(): void {
    this.registerTool('create_file', this.createFileTool);
    this.registerTool('modify_file', this.modifyFileTool);
    this.registerTool('delete_file', this.deleteFileTool);
  }

  registerTool(name: string, handler: IToolHandler): void {
    this.tools.set(name, handler);
  }

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

  getAvailableTools(): string[] {
    return Array.from(this.tools.keys());
  }
}
