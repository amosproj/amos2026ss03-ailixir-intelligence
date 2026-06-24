// Translates Firebase Auth errors into stable user-facing strings without
// leaking the raw Firebase code (which reads as gibberish to end users) and
// preserves the original code for log correlation / telemetry breadcrumbs.
//
// The fix #208 forensic dig surfaced two failure modes the previous catch
// block hid: (a) the same `INVALID_LOGIN_CREDENTIALS` covered both
// wrong-password and email-not-found, masking the actual reason; (b) the
// raw `"Firebase: Error (auth/...)"` string was rendered in the UI, which
// users read as "the app is broken." Mapping the code at the boundary
// fixes both.

import { FirebaseError } from 'firebase/app';

// Stable user-facing strings. Keep them short, neutral, and non-blaming.
// Add new entries here as new failure modes are observed in the wild.
const FIREBASE_AUTH_MESSAGES: Record<string, string> = {
  'auth/invalid-credential': 'Wrong email or password.',
  'auth/invalid-email': 'That email address looks invalid.',
  'auth/user-disabled': 'This account has been disabled. Contact support.',
  'auth/user-not-found': 'No account exists for that email.',
  'auth/wrong-password': 'Wrong email or password.',
  'auth/too-many-requests': 'Too many attempts. Please wait a few minutes and try again.',
  'auth/network-request-failed': 'No network connection. Check your internet and try again.',
  'auth/operation-not-allowed': 'Sign-in is temporarily disabled. Contact support.',
  'auth/email-already-in-use': 'An account already exists for that email.',
  'auth/weak-password': 'Password is too weak. Use at least 8 characters.',
};

const DEFAULT_USER_MESSAGE = 'Something went wrong. Please try again.';
const UNKNOWN_CODE = 'auth/unknown';

// Domain error type used throughout the auth flow. Carries:
//   - `code`: the originating Firebase `auth/...` code (for telemetry / tests)
//   - `userMessage`: the safe-to-render string for the UI
//   - `cause`: the original error, preserved so devtools / Sentry stack traces
//              still show the underlying Firebase exception.
export class AuthError extends Error {
  readonly code: string;
  readonly userMessage: string;

  constructor(cause: unknown) {
    const code = cause instanceof FirebaseError ? cause.code : UNKNOWN_CODE;
    const userMessage = FIREBASE_AUTH_MESSAGES[code] ?? DEFAULT_USER_MESSAGE;
    super(userMessage);
    this.name = 'AuthError';
    this.code = code;
    this.userMessage = userMessage;
    this.cause = cause;
  }
}

// Single point where we log the raw code. When Crashlytics / Sentry is wired
// up, swap the console.warn for a breadcrumb call — keeping the call site
// inside this module means no screen has to know about telemetry.
export function logAuthFailure(label: string, error: AuthError): void {
  console.warn(`[auth] ${label} failed`, {
    code: error.code,
    cause: error.cause instanceof Error ? error.cause.message : String(error.cause),
  });
}
