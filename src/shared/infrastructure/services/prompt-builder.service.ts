import { Injectable } from '@nestjs/common';
import { IPromptBuilderService } from '../../domain/interfaces/prompt-builder-service.interface';
import { HistoryEntry } from '../../domain/models/history-entry.model';

@Injectable()
export class PromptBuilderService implements IPromptBuilderService {
  buildSystemPrompt(currentHistory: HistoryEntry[], vaultContext?: string): string {
    let systemPrompt = `You are a helpful assistant. Respond to the user's queries based on the conversation history.`;

    if (vaultContext) {
      systemPrompt += `\n\nYou have access to the following vault context:\n\n${vaultContext}`;
    }

    return systemPrompt;
  }
}
