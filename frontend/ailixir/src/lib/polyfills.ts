if (typeof globalThis.DOMException === 'undefined') {
  const DOMException = class DOMException extends Error {
    constructor(message: string, name: string) {
      super(message);
      this.name = name;
    }
  } as unknown as typeof globalThis.DOMException;

  globalThis.DOMException = DOMException;
}
