import { Stack } from 'expo-router';
import React from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import { TamaguiProvider } from 'tamagui';
import { config } from '../tamagui.config';

// make imports typed
declare module 'tamagui' {
  // eslint-disable-next-line
  interface TamaguiCustomConfig extends Conf {}
}

export default function TabLayout() {
  const isLoggedIn = true;
  const loggedIn: boolean = Boolean(isLoggedIn);

  return (
    <TamaguiProvider config={config} defaultTheme="light">
      <SafeAreaView style={{ flex: 1 }}>
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Protected guard={loggedIn}>
            <Stack.Screen name="(private)" options={{ title: 'App' }} />
          </Stack.Protected>

          <Stack.Protected guard={!loggedIn}>
            <Stack.Screen name="(auth)" options={{ title: 'Auth' }} />
          </Stack.Protected>
        </Stack>
      </SafeAreaView>
    </TamaguiProvider>
  );
}
