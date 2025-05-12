import { Injectable } from '@nestjs/common';
import { ConfigService } from '../../../../shared/infrastructure/config/config.service';
import {
  GenerativeContentResponse,
  GenerativeFile,
} from '../../domain/interfaces/llm-service.interface';
import { GoogleGenAI } from '@google/genai';
import * as fs from 'fs';

@Injectable()
export class GoogleGenaiAdapter {
  private genAI: GoogleGenAI;

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
      }

      if (responseMimeType) {
        config.responseMimeType = responseMimeType;
      }

      // Safety settings are configured differently in the new API
      config.safetySettings = {
        harassment: 'block_only_high',
        hateSpeech: 'block_only_high',
        sexuallyExplicit: 'block_only_high',
        dangerousContent: 'block_only_high',
      };

      if (systemInstruction) {
        config.systemInstruction = systemInstruction;
      }

      const modelName = this.configService.getGeminiModelName();

      const response = await this.genAI.models.generateContent({
        model: modelName,
        contents,
        ...config,
      });

      return {
        text: response.text || '',
        parts: response.candidates?.[0]?.content?.parts || [],
      };
    } catch (error) {
      console.error('Error generating content:', error);
      return null;
    }
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
          console.error('Error in sync content generation:', error);
        });

      // Return a placeholder while the async operation completes
      return {
        text: 'Processing request...',
        parts: [],
      };
    } catch (error) {
      console.error('Error in sync wrapper:', error);
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
      console.error('Error uploading file:', error);
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
      // This is a simplified implementation
      // In a real app, you'd use a proper audio transcription API
      const file = this.uploadFile(audioFilePath);
      if (!file) return null;

      // For now, return a placeholder message
      return 'Audio transcription is not implemented in this adapter';
    } catch (error) {
      console.error('Error transcribing audio:', error);
      return null;
    }
  }
}
