export interface IVaultService {
  getVaultRoot(): string | undefined;

  resolvePath(relativePath: string): string | undefined;

  createFile(relativePath: string, content: string): Promise<boolean>;

  modifyFile(relativePath: string, content: string): Promise<boolean>;

  deleteFile(relativePath: string): Promise<boolean>;

  createFolder(relativePath: string): Promise<boolean>;

  deleteFolder(relativePath: string): Promise<boolean>;

  readFile(relativePath: string): Promise<string | undefined>;

  fileExists(relativePath: string): Promise<boolean>;

  folderExists(relativePath: string): Promise<boolean>;

  listFiles(relativePath?: string): Promise<string[] | undefined>;

  readAllMarkdownFiles(): Promise<Record<string, string>>;
}
