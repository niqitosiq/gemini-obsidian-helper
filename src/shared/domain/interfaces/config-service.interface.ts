export interface IConfigService {
  get<T>(key: string, defaultValue?: T): T;
  getStr(key: string, defaultValue?: string): string | undefined;
  getListStr(key: string, defaultValue?: string[]): string[] | undefined;
  getGeminiApiKey(): string | undefined;
  getGeminiModelName(): string;
  getTelegramBotToken(): string | undefined;
  getTelegramUserIds(): string[];
  getObsidianVaultPath(): string | undefined;
  getObsidianDailyNotesFolder(): string | undefined;
}
