import { ICommand } from '../../../../core/cqrs/commands/command.interface';
import { Task } from '../../domain/models/task.model';

export class SendTaskReminderCommand implements ICommand {
  readonly _commandBrand: symbol = Symbol('SendTaskReminderCommand');

  constructor(
    public readonly task: Task,
    public readonly minutesBefore: number = 15,
    public readonly userId?: number,
  ) {}
}
