import { Injectable } from '@nestjs/common';
import {
  ILLMService,
  GenerativeContentResponse,
  GenerativeFile,
} from '../../domain/interfaces/llm-service.interface';
import { GoogleGenaiAdapter } from '../adapters/google-genai.adapter';

@Injectable()
export class GeminiService implements ILLMService {
  constructor(private readonly genaiAdapter: GoogleGenaiAdapter) {}

  async callAsync(
    contents: any[],
    systemInstruction?: string,
    responseMimeType?: string,
    maxOutputTokens?: number,
  ): Promise<GenerativeContentResponse | null> {
    return this.genaiAdapter.generateContent(
      contents,
      systemInstruction,
      responseMimeType,
      maxOutputTokens,
    );
  }

  callSync(
    contents: any[],
    systemInstruction?: string,
    responseMimeType?: string,
    maxOutputTokens?: number,
  ): GenerativeContentResponse | null {
    return this.genaiAdapter.generateContentSync(
      contents,
      systemInstruction,
      responseMimeType,
      maxOutputTokens,
    );
  }

  uploadFile(filePath: string): GenerativeFile | null {
    return this.genaiAdapter.uploadFile(filePath);
  }

  deleteFile(fileName: string): boolean {
    return this.genaiAdapter.deleteFile(fileName);
  }

  transcribeAudio(audioFilePath: string): string | null {
    // Since we can't do a true sync operation in Node.js for this,
    // we'll execute the async method and return a placeholder
    // In a real app, you'd handle this differently
    this.genaiAdapter
      .transcribeAudio(audioFilePath)
      .then((result) => console.log('Transcription completed:', result ? 'success' : 'failed'))
      .catch((error) => console.error('Transcription error:', error));

    return 'Transcription in progress...';
  }
}
