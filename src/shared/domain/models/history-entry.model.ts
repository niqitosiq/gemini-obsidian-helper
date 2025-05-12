export interface HistoryEntryPart {
  text?: string;
}

export interface HistoryEntry {
  role: string; // 'user' or 'model'
  parts: HistoryEntryPart[];
}
