import { TamaguiProvider } from '@tamagui/core';
import { Stack } from 'expo-router';
import React from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';

import config from '@/tamagui.config';

export default function RootLayout() {
  const isLoggedIn = false;
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
