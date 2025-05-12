import { CommandHandler, ICommandHandler } from '@nestjs/cqrs';
import { ProcessMessageCommand } from './process-message.command';
import { LlmProcessorService } from '../../../llm/application/services/llm-processor.service';
import { Inject } from '@nestjs/common';
import { IVaultService } from '../../../vault/domain/interfaces/vault-service.interface';
import { ITelegramService } from '../../domain/interfaces/telegram-service.interface';

@CommandHandler(ProcessMessageCommand)
export class ProcessMessageHandler implements ICommandHandler<ProcessMessageCommand> {
  constructor(
    private readonly llmProcessor: LlmProcessorService,
    @Inject('IVaultService') private readonly vaultService: IVaultService,
    @Inject('ITelegramService') private readonly telegramService: ITelegramService,
  ) {}

  async execute(command: ProcessMessageCommand): Promise<void> {
    const { chatId, userId, text } = command.message;

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
      console.error('Error reading vault files:', error);
    }

    // Process the message
    const result = await this.llmProcessor.processUserMessage(text, userId, vaultContext);

    // Handle the result
    if (result.error) {
      await this.telegramService.sendMessage(chatId, `Error: ${result.error}`);
      return;
    }

    if (result.text) {
      await this.telegramService.sendMessage(chatId, result.text);
      return;
    }

    if (result.toolCalls && Array.isArray(result.toolCalls)) {
      // In a full implementation, we would handle tool calls here
      await this.telegramService.sendMessage(chatId, 'Processing tool calls...');
      return;
    }

    // Fallback
    await this.telegramService.sendMessage(
      chatId,
      'Received your message, but no response was generated.',
    );
  }
}
