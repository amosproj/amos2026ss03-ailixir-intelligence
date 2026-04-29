import { CText, CButton, CInput } from '@/components/atoms';
import { defaultConfig } from '@tamagui/config/v5';
import { TamaguiProvider, createTamagui } from '@tamagui/core';
import React from 'react';
import { Anchor, Button, Input, YStack } from 'tamagui';
import { Sun } from '@tamagui/lucide-icons-2';

// TODO: create a tamagui.config.ts file
const config = createTamagui(defaultConfig);

type Conf = typeof config;

// make imports typed
declare module '@tamagui/core' {
  interface TamaguiCustomConfig extends Conf {}
}

export default function TabLayout() {
  return (
    <TamaguiProvider config={config} defaultTheme="light">
      <YStack width="100%" height="100%" background="$background" justify="center" items="center" gap={5}>
        <CText fontSize={50} fontWeight={'bold'}>
          AiLixir
        </CText>
        <Button icon={Sun}>Hello World!</Button>
        <CInput placeholder="Type something..." width={300} />
      </YStack>
    </TamaguiProvider>
  );
}
