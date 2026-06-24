// Single public surface for Firebase Auth in the app.
//
// Before this hook existed, auth state was spread across three places:
//   - `_layout.tsx`           — onAuthStateChanged listener writing atoms
//   - `lib/authAtoms.ts`      — the atoms themselves
//   - `(auth)/login.tsx`      — direct `signInWithEmailAndPassword` call
//                               and ad-hoc `router.push` on success
// That spread was the structural reason behind #208: the screen pushed to
// a placeholder route at the exact moment the guard switched route groups,
// producing a non-deterministic race.
//
// The contract this hook enforces:
//   1. Imperative auth actions (signIn / signOut) never navigate.
//      Navigation is owned exclusively by `<Stack.Protected guard={isLoggedIn}>`
//      in `app/_layout.tsx`, driven by the same listener wired below.
//   2. All Firebase errors are normalised to `AuthError` at this boundary.
//   3. Email is trimmed + lowercased before Firebase ever sees it.
//      Removes the whole "trailing space from paste" / "iOS auto-cap" error
//      class without each screen having to remember.

import { useCallback, useEffect } from 'react';
import { useAtomValue, useSetAtom } from 'jotai';
import { onAuthStateChanged, signInWithEmailAndPassword, signOut as fbSignOut } from 'firebase/auth';

import { auth } from '@/lib/firebase';
import { authLoadingAtom, isLoggedInAtom, userAtom } from '@/lib/authAtoms';
import { AuthError, logAuthFailure } from '@/lib/auth-errors';

// Root-level subscription to Firebase's auth state. Mount in exactly ONE
// place (the root `_layout.tsx`) — every other consumer reads the atoms
// instead of subscribing to onAuthStateChanged itself.
export function useFirebaseAuthListener(): void {
  const setUser = useSetAtom(userAtom);
  const setAuthLoading = useSetAtom(authLoadingAtom);

  useEffect(() => {
    // First fire of `onAuthStateChanged` flips `authLoading` to false, which
    // unblocks the splash → guard transition in the root layout.
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setUser(user);
      setAuthLoading(false);
    });
    return unsubscribe;
  }, [setUser, setAuthLoading]);
}

// Consumer hook for screens. Reads reactive state from atoms and exposes
// imperative actions that throw `AuthError` on failure (so callers get one
// typed exception to handle, with a user-safe message ready to render).
export function useAuth() {
  const user = useAtomValue(userAtom);
  const isLoggedIn = useAtomValue(isLoggedInAtom);
  const isLoading = useAtomValue(authLoadingAtom);

  const signIn = useCallback(async (email: string, password: string): Promise<void> => {
    // Normalise email at the boundary — iOS keyboards routinely insert
    // trailing whitespace on paste and auto-capitalise the first letter.
    // Firebase Auth treats email case-insensitively for lookup but the
    // raw bytes still flow through this code path, and `.trim()` is the
    // cheapest fix for ~30% of "wrong password" support reports.
    const normalizedEmail = email.trim().toLowerCase();
    try {
      await signInWithEmailAndPassword(auth, normalizedEmail, password);
      // Deliberately NO router.push here. `Stack.Protected` in the root
      // layout will swap route groups the moment `userAtom` updates via
      // the listener above. Manual nav races that swap.
    } catch (cause) {
      const error = new AuthError(cause);
      logAuthFailure('signIn', error);
      throw error;
    }
  }, []);

  const signOut = useCallback(async (): Promise<void> => {
    try {
      await fbSignOut(auth);
    } catch (cause) {
      const error = new AuthError(cause);
      logAuthFailure('signOut', error);
      throw error;
    }
  }, []);

  return { user, isLoggedIn, isLoading, signIn, signOut };
}
