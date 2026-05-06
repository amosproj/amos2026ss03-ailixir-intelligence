import { Stack } from 'expo-router';
import { YStack } from 'tamagui';
import React from 'react';
import { AppBar } from '@/components/organisms';

export default function AuthLayout() {
  return (
    <YStack flex={1} background="$background">
      <AppBar />
      <Stack screenOptions={{ headerShown: false }} initialRouteName="login">
        <Stack.Screen name="login" options={{ title: 'Login' }} />
        <Stack.Screen name="signup" options={{ title: 'Create Account' }} />
        <Stack.Screen name="success" options={{ title: 'Success' }} />
      </Stack>
    </YStack>
  );
}
