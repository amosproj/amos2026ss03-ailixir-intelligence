import { initializeApp } from 'firebase/app';
import { initializeAuth, getReactNativePersistence } from 'firebase/auth';
import ReactNativeAsyncStorage from '@react-native-async-storage/async-storage';
import { firebaseConfig } from '@/firebase.config';

const app = initializeApp(firebaseConfig);

export const auth = initializeAuth(
  app,
  //   {
  //   persistence: getReactNativePersistence(ReactNativeAsyncStorage),
  // }
);
