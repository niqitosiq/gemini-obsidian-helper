import { IsNotEmpty, IsNumber, IsString } from 'class-validator';

export class MessageDto {
  @IsNumber()
  @IsNotEmpty()
  readonly chatId: number;

  @IsNumber()
  @IsNotEmpty()
  readonly userId: number;

  @IsString()
  @IsNotEmpty()
  readonly text: string;

  constructor(chatId: number, userId: number, text: string) {
    this.chatId = chatId;
    this.userId = userId;
    this.text = text;
  }
}
