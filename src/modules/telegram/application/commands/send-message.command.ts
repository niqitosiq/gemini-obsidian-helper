import { ICommand } from '@nestjs/cqrs';

export class SendMessageCommand {
  constructor(
    public readonly userId: number,
    public readonly message: string,
    public readonly parseMode?: 'Markdown' | 'HTML',
  ) {
    console.log('SendMessageCommand constructor CALLED');
    console.log(
      `SendMessageCommand handles command: ${SendMessageCommand.name}, Type: ${typeof SendMessageCommand}`,
    );
  }
}
