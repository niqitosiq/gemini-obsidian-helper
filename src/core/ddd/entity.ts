export abstract class Entity<T> {
  protected readonly id: T;
  
  constructor(id: T) {
    this.id = id;
  }

  public getId(): T {
    return this.id;
  }

  public equals(entity: Entity<T>): boolean {
    if (entity === null || entity === undefined) {
      return false;
    }
    
    if (this === entity) {
      return true;
    }
    
    return this.id === entity.id;
  }
} 