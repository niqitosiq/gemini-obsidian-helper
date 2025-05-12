export interface IQueryHandler<TQuery, TResult> {
  execute(query: TQuery): Promise<TResult>;
}

export abstract class QueryHandler<TQuery, TResult> implements IQueryHandler<TQuery, TResult> {
  abstract execute(query: TQuery): Promise<TResult>;
}
