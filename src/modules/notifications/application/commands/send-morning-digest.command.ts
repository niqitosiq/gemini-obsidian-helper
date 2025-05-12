import { ICommand } from '../../../../core/cqrs/commands/command.interface';

export class SendMorningDigestCommand implements ICommand {
  readonly _commandBrand: symbol = Symbol('SendMorningDigestCommand');

  constructor(public readonly userId: number) {}
}
