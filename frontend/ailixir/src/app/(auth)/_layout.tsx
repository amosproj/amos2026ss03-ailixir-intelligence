import { Stack } from 'expo-router';
import React from 'react';
import { YStack } from 'tamagui';

export default function AuthLayout() {
  return (
    <YStack flex={1} background="$background" px={20}>
      <Stack screenOptions={{ headerShown: false }} initialRouteName="login">
        <Stack.Screen name="login" options={{ title: 'Login' }} />
        <Stack.Screen name="signup" options={{ title: 'Create Account' }} />
        {/*
          No `success` screen. Post-signin navigation is owned exclusively
          by `Stack.Protected guard={isLoggedIn}` in the root layout — the
          (auth) group is unmounted the moment the listener flips
          `userAtom`, and the user is rendered into (private)/index. See
          issue #208 for the race condition that the placeholder route
          introduced.
        */}
      </Stack>
    </YStack>
  );
}
