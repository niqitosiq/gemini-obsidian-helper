import { ICommand } from '../../../../core/cqrs/commands/command.interface';
import { MessageDto } from '../../interface/dtos/message.dto';

export class ProcessMessageCommand implements ICommand {
  readonly _commandBrand: symbol = Symbol('ProcessMessageCommand');

  constructor(public readonly message: MessageDto) {}
}
