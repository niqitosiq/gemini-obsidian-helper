import { ICommand } from '../../../../core/cqrs/commands/command.interface';

export class SendEveningCheckInCommand implements ICommand {
  readonly _commandBrand: symbol = Symbol('SendEveningCheckInCommand');

  constructor(public readonly userId: number) {}
}
