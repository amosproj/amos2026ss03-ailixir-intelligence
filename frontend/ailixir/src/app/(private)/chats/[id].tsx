import { ChatMessages } from '@/components/organisms/';
import { ChatInput } from '@/components/molecules';
import { CText } from '@/components/atoms';
import React from 'react';
import { View, Platform, KeyboardAvoidingView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useHeaderHeight } from '@react-navigation/elements';
import { useLocalSearchParams } from 'expo-router';
import { FirebaseRuntimeProvider, useFirebaseRuntime } from '@/runtimes/firebase-runtime';

function ChatScreenContent() {
  const { messages, isRunning, sendMessage } = useFirebaseRuntime();
  const insets = useSafeAreaInsets();
  const headerHeight = useHeaderHeight();

  const handleReloadMessage = (messageId: string) => {
    console.log('Reload requested for:', messageId);
  };

  return (
    <KeyboardAvoidingView keyboardVerticalOffset={headerHeight} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
      <View style={{ flex: 1, backgroundColor: '#fff' }}>
        <ChatMessages messages={messages} onReloadMessage={handleReloadMessage} />
        <View
          style={{
            paddingLeft: 16,
            paddingRight: 16,
            paddingTop: 12,
            paddingBottom: Platform.OS === 'web' ? 12 : Math.max(insets.bottom, 12),
            borderTopWidth: 1,
            borderTopColor: '#e0e0e0',
          }}>
          <ChatInput onStartVoiceMode={() => alert('Voice mode not available')} onSendMessage={sendMessage} />
          <CText variant="caption" style={{ marginTop: 8, textAlign: 'center' }}>
            {isRunning ? 'AI is thinking...' : 'AI can make mistakes.'}
          </CText>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

export default function ChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();

  if (!id) return null;

  return (
    <FirebaseRuntimeProvider chatId={id}>
      <ChatScreenContent />
    </FirebaseRuntimeProvider>
  );
}
