import { ICommand } from '../../../../core/cqrs/commands/command.interface';

export class SendMessageCommand implements ICommand {
  readonly _commandBrand: symbol = Symbol('SendMessageCommand');

  constructor(
    public readonly chatId: number,
    public readonly text: string,
    public readonly parseMode?: string,
  ) {}
}
