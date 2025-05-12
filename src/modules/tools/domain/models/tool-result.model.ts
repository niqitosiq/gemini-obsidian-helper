export interface ToolResult {
  status: 'success' | 'error';
  message: string;
  [key: string]: any;
}
