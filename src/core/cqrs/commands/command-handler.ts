export interface ICommandHandler<TCommand> {
  execute(command: TCommand): Promise<void>;
}

export abstract class CommandHandler<TCommand> implements ICommandHandler<TCommand> {
  abstract execute(command: TCommand): Promise<void>;
}
