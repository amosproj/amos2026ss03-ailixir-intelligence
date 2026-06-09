import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Raleway_400Regular, Raleway_500Medium, Raleway_600SemiBold, Raleway_700Bold, useFonts } from '@expo-google-fonts/raleway';
import { Stack } from 'expo-router';
import React, { useEffect } from 'react';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaView } from 'react-native-safe-area-context';
import { TamaguiProvider, useTheme } from '@tamagui/core';
import { CText } from '@/components/atoms';
import { Circle, Spinner } from 'tamagui';
import { auth } from '@/lib/firebase';
import { authLoadingAtom, isLoggedInAtom, userAtom } from '@/lib/authAtoms';
import { onAuthStateChanged } from 'firebase/auth';
import { useAtomValue, useSetAtom } from 'jotai';
import { View } from 'react-native';
import { DefaultTheme, ThemeProvider } from '@react-navigation/native'; // 1. Navigation-Theme-Imports hinzufügen

import { config } from '@/tamagui.config';

void SplashScreen.preventAutoHideAsync();

function RootStackContent() {
  const theme = useTheme();
  const isLoggedIn = useAtomValue(isLoggedInAtom);
  const authLoading = useAtomValue(authLoadingAtom);
  const bgColor = theme.background.val as string;

  const NavTheme = {
    ...DefaultTheme,
    colors: {
      ...DefaultTheme.colors,
      background: bgColor,
    },
  };

  if (authLoading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <Spinner size="large" />
      </View>
    );
  }

  return (
    <ThemeProvider value={NavTheme}>
      <SafeAreaView style={{ flex: 1, backgroundColor: bgColor }}>
        <Stack
          screenOptions={{
            headerShown: true,
            headerShadowVisible: false,
            headerTitle: () => <CText variant="h1">AiLixir</CText>,
            headerRight: () => <Circle size={40} background="blue" mr={16} />,
          }}>
          <Stack.Protected guard={isLoggedIn}>
            <Stack.Screen name="(private)" options={{ title: 'App', headerShown: false }} />
          </Stack.Protected>

          <Stack.Protected guard={!isLoggedIn}>
            <Stack.Screen name="(auth)" options={{ title: 'Auth', headerShown: false }} />
          </Stack.Protected>
        </Stack>
      </SafeAreaView>
    </ThemeProvider>
  );
}

export default function RootStackNavigator() {
  const setUser = useSetAtom(userAtom);
  const setAuthLoading = useSetAtom(authLoadingAtom);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setUser(user);
      setAuthLoading(false);
    });
    return unsubscribe;
  }, [setUser, setAuthLoading]);

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

  if (!fontsLoaded) return null;

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <TamaguiProvider config={config} defaultTheme="light">
        <RootStackContent />
      </TamaguiProvider>
    </QueryClientProvider>
  );
}
