import { Stack } from 'expo-router';
import React from 'react';
import { YStack } from 'tamagui';

export default function AuthLayout() {
  return (
    <YStack flex={1} background="$background" px={20}>
      <Stack screenOptions={{ headerShown: false }} initialRouteName="login">
        <Stack.Screen name="login" options={{ title: 'Login' }} />
        <Stack.Screen name="signup" options={{ title: 'Create Account' }} />
      </Stack>
    </YStack>
  );
}
