import { router, Stack } from 'expo-router';
import React from 'react';
import { TouchableOpacity } from 'react-native';
import { ChevronLeft, Settings } from '@tamagui/lucide-icons-2';
import { CText } from '@/components/atoms';

export default function PrivateLayout() {
  return (
    <Stack
      initialRouteName="index"
      // show a back button automatically when the nav stack can go back
      screenOptions={({ navigation }) => ({
        headerShown: true,
        headerShadowVisible: false,
        headerLeft: () =>
          navigation.canGoBack() ? (
            <TouchableOpacity onPress={() => navigation.goBack()}>
              <ChevronLeft size={20} />
            </TouchableOpacity>
          ) : null,
        headerTitle: (props: any) => <CText variant="h1">{props?.children ?? props?.title ?? ''}</CText>,
      })}>
      <Stack.Screen
        name="index"
        options={{
          title: 'AiLixir',
          headerRight: () => (
            <TouchableOpacity onPress={() => router.navigate('/settings')}>
              <Settings size={20} />
            </TouchableOpacity>
          ),
        }}
      />
      <Stack.Screen name="settings" options={{ title: 'Settings' }} />
      <Stack.Screen name="chats/index" options={{ title: 'Chats' }} />
      <Stack.Screen name="chats/[id]" options={{ title: 'Chat' }} />
      <Stack.Screen name="documents/index" options={{ title: 'Documents' }} />
      <Stack.Screen name="documents/[id]" options={{ title: 'Document' }} />
      <Stack.Screen name="documents/capture" options={{ title: 'Capture' }} />
      <Stack.Screen name="documents/upload" options={{ title: 'Upload' }} />
    </Stack>
  );
}
