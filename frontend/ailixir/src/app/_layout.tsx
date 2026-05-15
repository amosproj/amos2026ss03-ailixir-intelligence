import { Raleway_400Regular, Raleway_500Medium, Raleway_600SemiBold, Raleway_700Bold, useFonts } from '@expo-google-fonts/raleway';
import { Stack } from 'expo-router';
import React from 'react';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaView } from 'react-native-safe-area-context';
import { TamaguiProvider, useTheme } from '@tamagui/core';
import { CText } from '@/components/atoms';
import { Circle } from 'tamagui';

import { config } from '@/tamagui.config';

void SplashScreen.preventAutoHideAsync();

function RootStackNavigator() {
  const theme = useTheme();
  const bgColor = theme.background.val as string;

  const [fontsLoaded] = useFonts({
    Raleway_400Regular,
    Raleway_500Medium,
    Raleway_600SemiBold,
    Raleway_700Bold,
  });

  React.useEffect(() => {
    if (fontsLoaded) {
      void SplashScreen.hideAsync();
    }
  }, [fontsLoaded]);

  if (!fontsLoaded) {
    return null;
  }

  const isLoggedIn = false;
  const loggedIn: boolean = Boolean(isLoggedIn);

  return (
    <SafeAreaView style={{ flex: 1 }}>
      <Stack
        screenOptions={{
          headerShown: true,
          headerStyle: { backgroundColor: bgColor },
          headerShadowVisible: false,
          headerTitle: () => <CText variant="h1">AiLixir</CText>,
          headerRight: () => <Circle size={40} background="blue" mr={16} />,
        }}>
        <Stack.Protected guard={loggedIn}>
          <Stack.Screen name="(private)" options={{ title: 'App', headerShown: false }} />
        </Stack.Protected>

        <Stack.Protected guard={!loggedIn}>
          <Stack.Screen name="(auth)" options={{ title: 'Auth' }} />
        </Stack.Protected>
      </Stack>
    </SafeAreaView>
  );
}

export default function TabLayout() {
  return (
    <TamaguiProvider config={config} defaultTheme="light">
      <RootStackNavigator />
    </TamaguiProvider>
  );
}
