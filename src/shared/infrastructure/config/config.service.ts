import { Injectable } from '@nestjs/common';
import { ConfigService as NestConfigService } from '@nestjs/config';
import { IConfigService } from '../../domain/interfaces/config-service.interface';
import * as path from 'path';

@Injectable()
export class ConfigService implements IConfigService {
  constructor(private readonly configService: NestConfigService) {}

  get<T>(key: string, defaultValue?: T): T {
    return this.configService.get<T>(key) ?? (defaultValue as T);
  }

  getStr(key: string, defaultValue?: string): string | undefined {
    return this.configService.get<string>(key) ?? defaultValue;
  }

  getListStr(key: string, defaultValue?: string[]): string[] | undefined {
    const value = this.configService.get<string>(key);
    if (!value) return defaultValue;
    return value.split(',').map((item) => item.trim());
  }

  getGeminiApiKey(): string | undefined {
    return this.getStr('GEMINI_API_KEY');
  }

  getGeminiModelName(): string {
    return this.getStr('GEMINI_MODEL_NAME', 'gemini-pro') as string;
  }

  getTelegramBotToken(): string | undefined {
    return this.getStr('TELEGRAM_BOT_TOKEN');
  }

  getTelegramUserIds(): string[] {
    const userIdsStr = this.configService.get<string>('TELEGRAM_USER_IDS', '');
    return userIdsStr
      .split(',')
      .map((id) => id.trim())
      .filter(Boolean);
  }

  getObsidianVaultPath(): string | undefined {
    return this.getStr('OBSIDIAN_VAULT_PATH');
  }

  getObsidianDailyNotesFolder(): string | undefined {
    return this.getStr('OBSIDIAN_DAILY_NOTES_FOLDER');
  }

  getPort(): number {
    return this.configService.get<number>('PORT', 3000);
  }
}
