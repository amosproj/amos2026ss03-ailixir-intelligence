/**
 * Debug toggles persisted across app sessions.
 *
 * `showOcrTextAtom` controls a debug card on the document detail screen
 * that displays the raw OCR text the backend extracted from the document.
 * Default OFF so demo/customer builds don't accidentally surface internal
 * pipeline output. The user flips it from the Settings screen.
 *
 * Persisted via `atomWithStorage` + AsyncStorage so the choice survives
 * app restarts — losing the toggle every cold start would be annoying
 * during debugging sessions.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { atomWithStorage, createJSONStorage } from 'jotai/utils';

// createJSONStorage returns a storage adapter that wraps AsyncStorage's
// promise-based API for jotai's expected sync-or-async interface.
// Without this wrap, atomWithStorage falls back to localStorage which
// doesn't exist in the React Native runtime.
const asyncStorage = createJSONStorage<boolean>(() => AsyncStorage);

export const showOcrTextAtom = atomWithStorage<boolean>('debug.showOcrText', false, asyncStorage);
