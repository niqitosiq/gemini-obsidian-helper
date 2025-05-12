import { Injectable } from '@nestjs/common';
import { QueryBus as NestQueryBus } from '@nestjs/cqrs';
import { IQuery } from './query.interface';

@Injectable()
export class QueryBus {
  constructor(private readonly nestQueryBus: NestQueryBus) {}

  async execute<T extends IQuery, R>(query: T): Promise<R> {
    return this.nestQueryBus.execute(query);
  }
}
