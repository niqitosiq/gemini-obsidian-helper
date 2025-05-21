import { Injectable, Inject, Logger, forwardRef } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { ToolsRegistryService } from '../../../tools/application/services/tools-registry.service';
import { GoogleGenaiAdapter } from '../../infrastructure/adapters/google-genai.adapter';
import { PromptBuilderService } from '../../../../shared/infrastructure/services/prompt-builder.service';
import { HistoryService } from '../../../../shared/infrastructure/persistence/history.service';
import { HistoryEntry } from '../../../../shared/domain/models/history-entry.model';

export interface LlmResponse {
  toolCalls: any[];
  error?: string;
}

@Injectable()
export class LlmProcessorService {
  private readonly logger = new Logger(LlmProcessorService.name);

  constructor(
    private readonly configService: ConfigService,
    @Inject(forwardRef(() => ToolsRegistryService))
    private readonly toolsRegistry: ToolsRegistryService,
    private readonly googleGenaiAdapter: GoogleGenaiAdapter,
    private readonly promptBuilder: PromptBuilderService,
    private readonly historyService: HistoryService,
  ) {}

  async processUserMessage(
    message: string,
    userId: number,
    vaultContext?: string,
  ): Promise<LlmResponse> {
    try {
      // Get user's message history
      const history = this.historyService.getHistory();

      // Build system prompt with vault context and tools
      let systemPrompt = this.promptBuilder.buildSystemPrompt(history, vaultContext);

      // Add strict formatting instructions to ensure JSON response
      // systemPrompt = this.addStrictFormattingInstructions(systemPrompt);

      // Add the current message to history
      const userEntry: HistoryEntry = {
        role: 'user',
        content: message,
        timestamp: new Date(),
      };
      this.historyService.appendEntry(userEntry);

      // Call the LLM through the adapter with proper system prompt
      const response = await this.googleGenaiAdapter.generateContent(
        [{ text: message }],
        systemPrompt,
      );

      if (!response) {
        return {
          toolCalls: [
            {
              tool: 'reply',
              params: {
                message: 'Failed to generate content from LLM. Please try again.',
              },
            },
          ],
          error: 'Failed to generate content from LLM',
        };
      }

      const responseText = response.text || '';

      // Log the raw response text for debugging
      this.logger.debug(`Raw LLM response: ${responseText.substring(0, 1000)}...`);

      // Try to extract tool calls from the response
      const toolCalls = this.extractToolCalls(responseText);

      if (toolCalls.length > 0) {
        this.logger.debug(`Extracted ${toolCalls.length} tool calls`);

        // Validate tool calls
        const validToolCalls = toolCalls.filter((call) => {
          const { tool, params } = call;
          if (!tool || typeof tool !== 'string') {
            this.logger.warn(`Invalid tool call: missing or invalid tool name`);
            return false;
          }

          if (!params || typeof params !== 'object') {
            this.logger.warn(`Invalid tool call for ${tool}: missing or invalid params`);
            return false;
          }

          // Check if the tool exists in the registry
          if (!this.toolsRegistry.hasToolHandler(tool)) {
            this.logger.warn(`Unknown tool in tool call: ${tool}`);
            return false;
          }

          return true;
        });

        // Add the LLM response to history
        const assistantEntry: HistoryEntry = {
          role: 'assistant',
          content: JSON.stringify(validToolCalls, null, 2),
          timestamp: new Date(),
        };
        this.historyService.appendEntry(assistantEntry);

        // If we have valid tool calls, return them
        if (validToolCalls.length > 0) {
          return {
            toolCalls: validToolCalls,
          };
        }

        // If all tool calls were invalid, create a reply tool call
        this.logger.warn('All extracted tool calls were invalid, creating synthetic reply');
        return {
          toolCalls: [
            {
              tool: 'reply',
              params: {
                message:
                  'I encountered an issue processing your request. Please try again with clearer instructions.',
              },
            },
          ],
        };
      }

      // If no valid tool calls were found, convert the raw text to a reply tool call
      this.logger.warn('No valid tool calls found in LLM response, converting to reply tool call');

      // Add the LLM response to history as plain text
      const assistantEntry: HistoryEntry = {
        role: 'assistant',
        content: responseText,
        timestamp: new Date(),
      };
      this.historyService.appendEntry(assistantEntry);

      // Create a synthetic tool call for the reply
      return {
        toolCalls: [
          {
            tool: 'reply',
            params: {
              message: responseText,
            },
          },
        ],
      };
    } catch (error) {
      this.logger.error(`Error processing message with LLM: ${error.message}`, error.stack);
      return {
        toolCalls: [
          {
            tool: 'reply',
            params: {
              message: `Sorry, I encountered an error: ${error.message || 'An error occurred while processing your message'}`,
            },
          },
        ],
        error: error.message || 'An error occurred while processing your message',
      };
    }
  }

  private addStrictFormattingInstructions(systemPrompt: string): string {
    const strictFormatInstructions = `
CRITICAL INSTRUCTION: Your response MUST ALWAYS be a valid JSON array of tool calls, NEVER plain text.

RESPONSE FORMAT:
1. ALWAYS respond with a JSON array of tool objects, even for simple replies
2. NEVER respond with plain text outside of the JSON structure
3. For any response to the user, use the "reply" tool with the message in the "data" field
4. Each tool object MUST have "tool" and "data" fields
5. The "tool" field must be one of the available tools
6. The "data" field must be an object with the appropriate parameters for that tool

INCORRECT (NEVER DO THIS):
"I'll help you with that task."

CORRECT (ALWAYS DO THIS):
[
  {
    "tool": "reply",
    "data": {
      "message": "I'll help you with that task."
    }
  }
]

If you need to respond to the user, ALWAYS use the "reply" tool, never plain text.

Remember:
- Never output any text that isn't part of the JSON array
- No explanations, preambles, or postscripts outside the JSON
- Every response must be a JSON array, even if it's just a simple message
- The JSON array must be valid and parseable
`;

    return systemPrompt + '\n\n' + strictFormatInstructions;
  }

  private extractToolCalls(text: string): any[] {
    const toolCalls = [];

    // Clean up the text - remove any text before and after the array
    // This is critical for handling cases where the LLM includes explanations
    let cleanedText = text.trim();

    // Find the first '[' and last ']' to extract the array
    const startIndex = cleanedText.indexOf('[');
    const endIndex = cleanedText.lastIndexOf(']');

    if (startIndex !== -1 && endIndex !== -1 && endIndex > startIndex) {
      cleanedText = cleanedText.substring(startIndex, endIndex + 1);
    }

    // Try to parse the cleaned text as JSON array
    try {
      const parsedJson = JSON.parse(cleanedText);

      if (Array.isArray(parsedJson)) {
        for (const item of parsedJson) {
          if (item && typeof item === 'object') {
            // Support both "data" and "params" keys for compatibility
            const toolName = item.tool;
            const toolParams = item.data || item.params;

            if (toolName && toolParams) {
              toolCalls.push({
                tool: toolName,
                params: toolParams,
              });
            } else {
              this.logger.warn(
                `Item in JSON array missing required fields: ${JSON.stringify(item)}`,
              );
            }
          }
        }

        if (toolCalls.length > 0) {
          return toolCalls;
        } else {
          this.logger.warn('JSON array parsed but no valid tool calls found');
        }
      } else {
        this.logger.warn('Parsed JSON is not an array');
      }
    } catch (e) {
      this.logger.warn(`Failed to parse text as JSON array: ${e.message}`);

      // If we couldn't parse the whole text, try to find JSON arrays inside it
      try {
        // Find JSON array in the text - look for arrays starting with [ and ending with ]
        const jsonRegex = /\[[\s\S]*?\]/g;
        const jsonMatches = text.match(jsonRegex);

        if (jsonMatches) {
          for (const jsonMatch of jsonMatches) {
            try {
              const parsedJson = JSON.parse(jsonMatch);
              if (Array.isArray(parsedJson)) {
                for (const item of parsedJson) {
                  if (item.tool && (item.data || item.params)) {
                    toolCalls.push({
                      tool: item.tool,
                      params: item.data || item.params,
                    });
                  }
                }
                // If we found tool calls in this JSON, we can return early
                if (toolCalls.length > 0) {
                  return toolCalls;
                }
              }
            } catch (e) {
              // Continue to next match if this one isn't valid JSON
              this.logger.debug(`Failed to parse JSON match: ${e.message}`);
            }
          }
        }
      } catch (e) {
        this.logger.warn(`Error in regex JSON extraction: ${e.message}`);
      }

      // Last resort: try the old [[tool:name]] format
      try {
        const toolCallRegex = /\[\[tool:(\w+)\]\]([\s\S]*?)\[\[\/tool\]\]/g;

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
            this.logger.error(`Error parsing tool call params for ${toolName}: ${error.message}`);
          }
        }
      } catch (e) {
        this.logger.warn(`Error with regex tool extraction: ${e.message}`);
      }
    }

    return toolCalls;
  }
}
