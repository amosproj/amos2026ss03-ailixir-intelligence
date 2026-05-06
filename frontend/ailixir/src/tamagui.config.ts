import { createSystemFont, defaultConfig } from '@tamagui/config/v5';
import { createTamagui } from '@tamagui/core';
import { Platform } from 'react-native';

// Font setup from theme.ts
const fontFamily = Platform.select({
  ios: 'system-ui',
  android: 'Roboto',
  web: 'var(--font-display)',
  default: 'system-ui',
});

const bodyFont = createSystemFont({
  font: {
    family: fontFamily,
  },
});

const headingFont = createSystemFont({
  font: {
    family: fontFamily,
    weight: {
      7: '700',
    },
  },
});

const config = createTamagui({
  ...defaultConfig,
  fonts: {
    ...defaultConfig.fonts,
    body: bodyFont,
    heading: headingFont,
  },
});

export type Conf = typeof config;

// make imports typed
declare module '@tamagui/core' {
  // eslint-disable-next-line
  interface TamaguiCustomConfig extends Conf {}
}

export default config;
