import { AppBar } from '@/components/organisms';
import { Stack } from 'expo-router';
import React from 'react';

export default function PrivateLayout() {
  return (
    <>
      <AppBar />
      <Stack screenOptions={{ headerShown: false }} initialRouteName="index">
        <Stack.Screen name="settings" options={{ title: 'Settings' }} />
        <Stack.Screen name="chats" options={{ title: 'Chats' }} />
        <Stack.Screen name="chats/[id]" options={{ title: 'Chat' }} />
        <Stack.Screen name="documents" options={{ title: 'Documents' }} />
        <Stack.Screen name="documents/[id]" options={{ title: 'Document' }} />
        <Stack.Screen name="documents/capture" options={{ title: 'Capture' }} />
        <Stack.Screen name="documents/upload" options={{ title: 'Upload' }} />
      </Stack>
    </>
  );
}
