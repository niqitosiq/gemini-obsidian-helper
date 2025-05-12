export interface IToolHandler {
  execute(params: Record<string, any>): Promise<Record<string, any>>;
}
