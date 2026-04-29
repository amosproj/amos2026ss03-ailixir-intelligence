import { defaultConfig } from '@tamagui/config/v5';
import { TamaguiProvider, createTamagui } from '@tamagui/core';
import { Stack } from 'expo-router';
import React from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';

// TODO: create a tamagui.config.ts file
const config = createTamagui(defaultConfig);

type Conf = typeof config;

// make imports typed
declare module '@tamagui/core' {
  // eslint-disable-next-line
  interface TamaguiCustomConfig extends Conf {}
}

export default function TabLayout() {
  return (
    <TamaguiProvider config={config} defaultTheme="light">
      <SafeAreaView style={{ flex: 1 }}>
        <Stack screenOptions={{ headerShown: false }} />
      </SafeAreaView>
    </TamaguiProvider>
  );
}
