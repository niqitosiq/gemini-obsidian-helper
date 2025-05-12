export interface IRecurringEventsEngine {
  loadAndScheduleAll(): Promise<void>;

  start(): Promise<void>;

  stop(): Promise<void>;

  handleVaultFileEvent(relativePath: string): Promise<void>;
}
