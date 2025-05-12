import { HistoryEntry } from '../models/history-entry.model';

export interface IPromptBuilderService {
  buildSystemPrompt(currentHistory: HistoryEntry[], vaultContext?: string): string;
}
