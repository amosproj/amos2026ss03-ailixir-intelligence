/**
 * Polyfill for globalThis.DOMException.
 *
 * In React Native (especially when using the Hermes engine), `DOMException` is not available in the global scope.
 * However, WebRTC and LiveKit dependencies require it to be defined globally.
 * This file polyfills `DOMException` so that LiveKit can load and execute correctly.
 *
 * Note: This file must be imported before any WebRTC/LiveKit packages are loaded to prevent runtime errors.
 */
if (typeof globalThis.DOMException === 'undefined') {
  const DOMException = class DOMException extends Error {
    constructor(message: string, name: string) {
      super(message);
      this.name = name;
    }
  } as unknown as typeof globalThis.DOMException;

  globalThis.DOMException = DOMException;
}
