import { defaultConfig } from '@tamagui/config/v5';
import { createFont, createTamagui, isWeb } from 'tamagui';
import { themes } from './themes';

const ralewayFont = createFont({
  family: isWeb ? 'Raleway, sans-serif' : 'Raleway',
  size: {
    1: 12,
    2: 14,
    3: 16,
    4: 18,
    5: 20,
    6: 22,
    7: 24,
    8: 28,
    9: 32,
  },
  face: {
    100: { normal: 'Raleway_400Regular' },
    200: { normal: 'Raleway_400Regular' },
    300: { normal: 'Raleway_400Regular' },
    400: { normal: 'Raleway_400Regular' },
    500: { normal: 'Raleway_500Medium' },
    600: { normal: 'Raleway_600SemiBold' },
    700: { normal: 'Raleway_700Bold' },
    800: { normal: 'Raleway_700Bold' },
    900: { normal: 'Raleway_700Bold' },
  },
});

export const config = createTamagui({
  ...defaultConfig,
  fonts: {
    ...defaultConfig.fonts,
    body: ralewayFont,
    heading: ralewayFont,
  },
  themes,
});

export type AppConfig = typeof config;

declare module 'tamagui' {
  // Tamagui requires this empty interface for module augmentation so AppConfig is merged into Tamagui types.
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface TamaguiCustomConfig extends AppConfig {}
}

export default config;
