export interface GenerativeContentResponse {
  text?: string;
  parts?: { text?: string }[];
}

export interface GenerativeFile {
  name: string;
  data: any;
}

export interface ILLMService {
  callAsync(
    contents: any[],
    systemInstruction?: string,
    responseMimeType?: string,
    maxOutputTokens?: number,
  ): Promise<GenerativeContentResponse | null>;

  callSync(
    contents: any[],
    systemInstruction?: string,
    responseMimeType?: string,
    maxOutputTokens?: number,
  ): GenerativeContentResponse | null;

  uploadFile(filePath: string): GenerativeFile | null;

  deleteFile(fileName: string): boolean;

  transcribeAudio(audioFilePath: string): string | null;
}
