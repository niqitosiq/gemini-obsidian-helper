import { Inject, Logger, forwardRef, Injectable } from '@nestjs/common';
import {
  LlmProcessorService,
  LlmResponse,
} from '../../../llm/application/services/llm-processor.service';
import { IVaultService } from '../../../vault/domain/interfaces/vault-service.interface';
import { ITelegramService } from '../../domain/interfaces/telegram-service.interface';
import { ToolsRegistryService } from '../../../tools/application/services/tools-registry.service';
import { VaultService } from 'src/modules/vault/infrastructure/services/vault.service';
import { MessageDto } from '../../interface/dtos/message.dto';

@Injectable()
export class ProcessMessageService {
  private readonly logger = new Logger(ProcessMessageService.name);

  constructor(
    @Inject(forwardRef(() => LlmProcessorService))
    private readonly llmProcessor: LlmProcessorService,
    private readonly vaultService: VaultService,
    private readonly toolsRegistry: ToolsRegistryService,
  ) {}

  async processMessage(message: MessageDto): Promise<void> {
    const { chatId, userId, text } = message;

    // Get vault context
    let vaultContext: string | undefined;
    try {
      const vaultFiles = await this.vaultService.readAllMarkdownFiles();
      if (vaultFiles && Object.keys(vaultFiles).length > 0) {
        const vaultContextParts = Object.entries(vaultFiles).map(
          ([path, content]) => `File: ${path}\n\n\`\`\`\n${content}\n\`\`\`\n\n`,
        );
        vaultContext = vaultContextParts.join('');

        // Truncate if too large
        if (vaultContext.length > 150000) {
          vaultContext = vaultContext.substring(0, 150000) + '\n... (truncated)';
        }
      }
    } catch (error) {
      this.logger.error('Error reading vault files:', error);
    }

    try {
      // Process the message
      const result = await this.llmProcessor.processUserMessage(text, userId, vaultContext);
      await this.executeToolCalls(result, undefined, chatId);
    } catch (error) {
      this.logger.error(`Error in ProcessMessageService: ${error.message}`, error.stack);
      await this.toolsRegistry.executeTool('reply', {
        message: `Error processing your message: ${error.message}`,
        chat_id: chatId,
      });
    }
  }

  public async executeToolCalls(
    response: LlmResponse,
    userId?: string,
    chatId?: number,
  ): Promise<void> {
    if (response.toolCalls && Array.isArray(response.toolCalls) && response.toolCalls.length > 0) {
      this.logger.debug(`Executing ${response.toolCalls.length} tool calls`);
      for (const toolCall of response.toolCalls) {
        const { tool, params } = toolCall;
        this.logger.debug(`Executing tool: ${tool}`);

        // Add chat_id to params if not present for appropriate tools
        if (tool === 'reply' && params && !params.chat_id) {
          params.chat_id = chatId;
        }

        if (tool === 'reply' && params && !params.user_id) {
          params.user_id = userId;
        }

        await this.toolsRegistry.executeTool(tool, params);
      }
    } else {
      // Fallback error case - should never happen with updated LlmProcessorService
      this.logger.error('No tool calls returned from LLM processor');
      await this.toolsRegistry.executeTool('reply', {
        message: 'Error: Received your message, but no valid response was generated.',
        chat_id: chatId,
        user_id: userId,
      });
    }
  }
}
