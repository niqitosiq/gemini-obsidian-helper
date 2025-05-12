export abstract class ValueObject {
  public abstract equals(vo: ValueObject): boolean;

  protected static areEqual(a: ValueObject, b: ValueObject): boolean {
    if (a === null || a === undefined || b === null || b === undefined) {
      return false;
    }

    return a.equals(b);
  }
}
