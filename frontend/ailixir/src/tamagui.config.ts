import { defaultConfig } from '@tamagui/config/v5';
import { createTamagui } from 'tamagui';

export const config = createTamagui(defaultConfig);

export type AppConfig = typeof config;

declare module 'tamagui' {
  // Tamagui requires this empty interface for module augmentation so AppConfig is merged into Tamagui types.
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface TamaguiCustomConfig extends AppConfig {}
}

export default config;
