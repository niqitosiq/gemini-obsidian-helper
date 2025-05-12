import { HistoryEntry } from '../models/history-entry.model';

export interface IHistoryService {
  load(): void;
  getHistory(): HistoryEntry[];
  appendEntry(entry: HistoryEntry): void;
  clearHistory(): void;
  setHistory(history: HistoryEntry[]): void;
}
