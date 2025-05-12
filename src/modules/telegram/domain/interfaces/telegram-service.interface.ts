export interface ITelegramService {
  setCurrentContext(update: any, context: any): void;

  sendMessage(chatId: number, text: string, parseMode?: string): Promise<boolean>;

  sendMessageToUser(userId: number, text: string, parseMode?: string): Promise<boolean>;

  replyToCurrentMessage(text: string, parseMode?: string): Promise<boolean>;
}
