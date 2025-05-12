import { Injectable } from '@nestjs/common';
import { IHistoryService } from '../../domain/interfaces/history-service.interface';
import { HistoryEntry } from '../../domain/models/history-entry.model';
import * as fs from 'fs';
import * as path from 'path';

@Injectable()
export class HistoryService implements IHistoryService {
  private history: HistoryEntry[] = [];
  private readonly historyFilePath: string = path.join(process.cwd(), 'conversation_history.json');
  private isLoaded = false;

  load(): void {
    if (this.isLoaded) return;

    try {
      if (fs.existsSync(this.historyFilePath)) {
        const fileContent = fs.readFileSync(this.historyFilePath, 'utf8');
        this.history = JSON.parse(fileContent);
      } else {
        this.history = [];
        this.saveHistory();
      }
      this.isLoaded = true;
    } catch (error) {
      console.error('Error loading history:', error);
      this.history = [];
    }
  }

  getHistory(): HistoryEntry[] {
    if (!this.isLoaded) this.load();
    return [...this.history];
  }

  appendEntry(entry: HistoryEntry): void {
    if (!this.isLoaded) this.load();
    this.history.push(entry);
    this.saveHistory();
  }

  clearHistory(): void {
    this.history = [];
    this.saveHistory();
  }

  setHistory(history: HistoryEntry[]): void {
    this.history = [...history];
    this.saveHistory();
  }

  private saveHistory(): void {
    try {
      fs.writeFileSync(this.historyFilePath, JSON.stringify(this.history, null, 2), 'utf8');
    } catch (error) {
      console.error('Error saving history:', error);
    }
  }
}
