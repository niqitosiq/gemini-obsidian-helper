import { Injectable } from '@nestjs/common';
import { CommandBus as NestCommandBus } from '@nestjs/cqrs';
import { ICommand } from './command.interface';

@Injectable()
export class CommandBus {
  constructor(private readonly nestCommandBus: NestCommandBus) {}

  async execute<T extends ICommand>(command: T): Promise<any> {
    return this.nestCommandBus.execute(command);
  }
}
