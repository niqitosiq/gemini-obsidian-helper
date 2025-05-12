import { HistoryEntry } from '../models/history-entry.model';

export interface IPromptBuilderService {
  /**
   * Builds a system prompt for the LLM with instructions, tool descriptions,
   * examples, and optional vault context.
   *
   * @param history - Array of conversation history entries
   * @param vaultContext - Optional context from the vault files
   * @returns The complete system prompt as a string
   */
  buildSystemPrompt(history: HistoryEntry[], vaultContext?: string): string;
}
