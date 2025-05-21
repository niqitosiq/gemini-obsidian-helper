/**
 * Interface for tool handlers
 * Defines the contract for classes that implement tool functionality
 */
export interface IToolHandler {
  /**
   * Execute the tool with the provided parameters
   *
   * @param params - Parameters for the tool execution
   * @returns Result of the tool execution
   */
  execute(params: Record<string, any>): Promise<Record<string, any>>;
}
