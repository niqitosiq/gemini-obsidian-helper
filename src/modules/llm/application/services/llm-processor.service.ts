import { Injectable, Inject } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ToolsRegistryService } from '../../../tools/application/services/tools-registry.service';
import { GoogleGenaiAdapter } from '../../infrastructure/adapters/google-genai.adapter';

interface LlmResponse {
  text?: string;
  toolCalls?: any[];
  error?: string;
}

@Injectable()
export class LlmProcessorService {
  constructor(
    private readonly configService: ConfigService,
    private readonly toolsRegistry: ToolsRegistryService,
    private readonly googleGenaiAdapter: GoogleGenaiAdapter,
  ) {}

  async processUserMessage(
    message: string,
    userId: number,
    vaultContext?: string,
  ): Promise<LlmResponse> {
    try {
      // Prepare the prompt with context if available
      let prompt = message;
      if (vaultContext) {
        prompt = `Context from vault:\n${vaultContext}\n\nUser message: ${message}`;
      }

      // Get available tools
      const availableTools = this.toolsRegistry.getAvailableTools();
      const toolsDescription = `Available tools: ${availableTools.join(', ')}`;

      // Combine prompt with tools description
      const fullPrompt = `${prompt}\n\n${toolsDescription}`;

      // Call the LLM through the adapter
      const response = await this.googleGenaiAdapter.generateContent([{ text: fullPrompt }]);

      if (!response) {
        return {
          error: 'Failed to generate content from LLM',
        };
      }

      const text = response.text || '';

      // Check for tool calls in the response
      // This is a simplified implementation - in a real app, you'd parse the response
      // to detect and execute tool calls
      const toolCalls = this.extractToolCalls(text);

      if (toolCalls.length > 0) {
        return {
          toolCalls,
        };
      }

      return {
        text,
      };
    } catch (error) {
      console.error('Error processing message with LLM:', error);
      return {
        error: error.message || 'An error occurred while processing your message',
      };
    }
  }

  private extractToolCalls(text: string): any[] {
    // This is a simplified implementation
    // In a real app, you'd use a more robust parser
    const toolCallRegex = /\[\[tool:(\w+)\]\]([\s\S]*?)\[\[\/tool\]\]/g;
    const toolCalls = [];

    let match;
    while ((match = toolCallRegex.exec(text)) !== null) {
      const toolName = match[1];
      const paramsStr = match[2].trim();

      try {
        const params = JSON.parse(paramsStr);
        toolCalls.push({
          tool: toolName,
          params,
        });
      } catch (error) {
        console.error(`Error parsing tool call params for ${toolName}:`, error);
      }
    }

    return toolCalls;
  }
}
