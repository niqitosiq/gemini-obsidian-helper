import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '../../../../shared/infrastructure/config/config.service';
import {
  GenerativeContentResponse,
  GenerativeFile,
} from '../../domain/interfaces/llm-service.interface';
import { GoogleGenAI, createUserContent, createPartFromUri } from '@google/genai';
import * as fs from 'fs';

@Injectable()
export class GoogleGenaiAdapter {
  private genAI: GoogleGenAI;
  private readonly logger = new Logger(GoogleGenaiAdapter.name);

  constructor(private readonly configService: ConfigService) {
    const apiKey = this.configService.getGeminiApiKey();
    if (!apiKey) {
      throw new Error('Gemini API key is not configured');
    }

    this.genAI = new GoogleGenAI({ apiKey });
  }

  async generateContent(
    contents: any[],
    systemInstruction?: string,
    responseMimeType?: string,
    maxOutputTokens?: number,
  ): Promise<GenerativeContentResponse | null> {
    try {
      const config: any = {};

      if (maxOutputTokens) {
        config.maxOutputTokens = maxOutputTokens;
      } else {
        // Default to a reasonable token limit
        config.maxOutputTokens = 1000000;
      }

      // Always set response format to JSON
      config.responseMimeType = 'application/json';

      // Set generation config to prefer structured output
      config.generationConfig = {
        temperature: 0.04, // Extremely low temperature for deterministic outputs
        topP: 0.95,
        topK: 40,
      };

      config.systemInstruction = systemInstruction;

      const modelName = this.configService.getGeminiModelName() || 'gemini-2.0-flash';

      this.logger.debug(`Calling Gemini model: ${modelName}`);
      const response = await this.genAI.models.generateContent({
        model: modelName,
        contents,
        config,
      });

      // Get the raw response text
      let responseText = response.text || '';
      this.logger.debug(`Raw response from Gemini: ${responseText.substring(0, 200)}...`);

      // Process the response to ensure it's valid JSON
      responseText = this.processResponse(responseText);

      return {
        text: responseText,
        parts: response.candidates?.[0]?.content?.parts || [],
      };
    } catch (error) {
      this.logger.error(`Error generating content from Gemini: ${error.message}`, error.stack);
      return null;
    }
  }

  /**
   * Process the LLM response to ensure it's a valid JSON array of tool calls
   */
  private processResponse(text: string): string {
    try {
      // Clean up the response text - extract just the JSON array
      const extractedJson = this.extractJsonArray(text);

      // Validate the JSON
      const parsed = JSON.parse(extractedJson);

      if (!Array.isArray(parsed)) {
        throw new Error('Response is not a JSON array');
      }

      if (parsed.length === 0) {
        throw new Error('Response JSON array is empty');
      }

      // Check if all items have the expected structure
      const hasValidStructure = parsed.every((item) => item.tool && (item.data || item.params));

      if (!hasValidStructure) {
        throw new Error('Response JSON does not have the expected tool call structure');
      }

      // If we got here, the JSON is valid
      this.logger.debug('Successfully parsed valid JSON tool call array');
      return extractedJson;
    } catch (e) {
      // If it's not valid JSON or doesn't have the expected structure, wrap it in a reply tool call
      this.logger.warn(`Error parsing LLM response as JSON: ${e.message}`);

      // Create a proper tool call that includes the original text
      return JSON.stringify([
        {
          tool: 'reply',
          data: {
            message: `I need to respond with proper tool calls. Here's what I meant to say: ${text.substring(0, 500)}...`,
          },
        },
      ]);
    }
  }

  /**
   * Extract a JSON array from text, handling various formats and edge cases
   */
  private extractJsonArray(text: string): string {
    // First, clean up the text
    let cleanedText = text.trim();

    // If it already starts with [ and ends with ], assume it's already a JSON array
    if (cleanedText.startsWith('[') && cleanedText.endsWith(']')) {
      try {
        // Verify it's valid JSON
        JSON.parse(cleanedText);
        return cleanedText;
      } catch (e) {
        // If parsing fails, continue with extraction attempts
        this.logger.debug(`Text looks like JSON array but parsing failed: ${e.message}`);
      }
    }

    // Try to find the first [ and last ]
    const startIndex = cleanedText.indexOf('[');
    const endIndex = cleanedText.lastIndexOf(']');

    if (startIndex !== -1 && endIndex !== -1 && endIndex > startIndex) {
      // Extract what looks like a JSON array
      const potentialJson = cleanedText.substring(startIndex, endIndex + 1);
      try {
        // Verify it's valid JSON
        JSON.parse(potentialJson);
        return potentialJson;
      } catch (e) {
        // If parsing fails, continue with other extraction attempts
        this.logger.debug(`Extracted potential JSON but parsing failed: ${e.message}`);
      }
    }

    // If we couldn't find a JSON array, look for multiple possible JSON arrays
    const jsonRegex = /\[[\s\S]*?\]/g;
    const matches = cleanedText.match(jsonRegex);

    if (matches && matches.length > 0) {
      // Try each match to find valid JSON
      for (const match of matches) {
        try {
          const parsed = JSON.parse(match);
          if (Array.isArray(parsed) && parsed.length > 0) {
            return match;
          }
        } catch (e) {
          // Continue to next match
          this.logger.debug(`Failed to parse potential JSON match: ${e.message}`);
        }
      }
    }

    // If we couldn't find any valid JSON arrays, wrap the text in a reply tool call
    this.logger.warn('Could not extract valid JSON array, creating synthetic tool call');
    return JSON.stringify([
      {
        tool: 'reply',
        data: {
          message: cleanedText.substring(0, 1000), // Limit to 1000 chars to avoid huge responses
        },
      },
    ]);
  }

  generateContentSync(
    contents: any[],
    systemInstruction?: string,
    responseMimeType?: string,
    maxOutputTokens?: number,
  ): GenerativeContentResponse | null {
    // In Node.js environment, we can't truly do sync API calls
    // This is a wrapper that executes the async call and returns the result or null
    try {
      // Execute the promise and wait for the result
      let result: GenerativeContentResponse | null = null;

      // Start the async operation
      this.generateContent(contents, systemInstruction, responseMimeType, maxOutputTokens)
        .then((response) => {
          result = response;
        })
        .catch((error) => {
          this.logger.error('Error in sync content generation:', error);
        });

      // Return a placeholder while the async operation completes
      return {
        text: 'Processing request...',
        parts: [],
      };
    } catch (error) {
      this.logger.error('Error in sync wrapper:', error);
      return null;
    }
  }

  uploadFile(filePath: string): GenerativeFile | null {
    try {
      const fileData = fs.readFileSync(filePath);
      const fileName = filePath.split('/').pop() || 'unknown';

      return {
        name: fileName,
        data: fileData,
      };
    } catch (error) {
      this.logger.error('Error uploading file:', error);
      return null;
    }
  }

  deleteFile(fileName: string): boolean {
    // Google GenAI doesn't have a concept of deleting uploaded files
    // This is a placeholder for compatibility
    return true;
  }

  async transcribeAudio(audioFilePath: string): Promise<string | null> {
    try {
      // Upload the audio file to Gemini
      const mimeType = this.getMimeType(audioFilePath);
      const myfile = await this.genAI.files.upload({
        file: String(audioFilePath),
        config: { mimeType },
      });
      // Prepare the prompt for transcription
      const prompt = 'Generate a transcript of the speech.';
      // Ensure model name is always a string
      const modelName = this.configService.getGeminiModelName() || 'gemini-2.0-flash';
      // Send the file and prompt to Gemini
      const response = await this.genAI.models.generateContent({
        model: modelName,
        contents: createUserContent([createPartFromUri(myfile.uri!, myfile.mimeType!), prompt]),
      });
      return response.text || null;
    } catch (error) {
      this.logger.error('Error transcribing audio with Gemini:', error);
      return null;
    }
  }

  /**
   * Get the MIME type for a given audio file path
   */
  private getMimeType(filePath: string): string {
    if (filePath.endsWith('.mp3')) return 'audio/mp3';
    if (filePath.endsWith('.wav')) return 'audio/wav';
    if (filePath.endsWith('.ogg')) return 'audio/ogg';
    if (filePath.endsWith('.aac')) return 'audio/aac';
    if (filePath.endsWith('.flac')) return 'audio/flac';
    if (filePath.endsWith('.aiff')) return 'audio/aiff';
    return 'application/octet-stream';
  }
}
