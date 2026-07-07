import '@/lib/polyfills';

import { registerRootComponent } from 'expo';
import { ExpoRoot } from 'expo-router';
import { TamaguiProvider } from 'tamagui';
import { config } from './src/tamagui.config';

function App() {
  const ctx = require.context('./src/app');

  return (
    <TamaguiProvider config={config} defaultTheme="light">
      <ExpoRoot context={ctx} />
    </TamaguiProvider>
  );
}

registerRootComponent(App);
