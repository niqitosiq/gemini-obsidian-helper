/**
 * Represents an entry in the conversation history between the user and the assistant.
 */
export class HistoryEntry {
  /**
   * Creates a new history entry.
   *
   * @param role - The role of the message sender ('user' or 'assistant')
   * @param content - The content of the message
   * @param timestamp - The timestamp when the message was created (defaults to now)
   */
  constructor(
    public readonly role: 'user' | 'assistant',
    public readonly content: string,
    public readonly timestamp: Date = new Date(),
  ) {}

  /**
   * Creates a user message history entry.
   *
   * @param content - The content of the user message
   * @returns A new HistoryEntry with role 'user'
   */
  static fromUser(content: string): HistoryEntry {
    return new HistoryEntry('user', content);
  }

  /**
   * Creates an assistant message history entry.
   *
   * @param content - The content of the assistant message
   * @returns A new HistoryEntry with role 'assistant'
   */
  static fromAssistant(content: string): HistoryEntry {
    return new HistoryEntry('assistant', content);
  }
}
