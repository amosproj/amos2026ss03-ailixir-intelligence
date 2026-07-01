import { ChatMessages } from '@/components/organisms/';
import { ChatInput } from '@/components/molecules';
import { CText } from '@/components/atoms';
import React, { useEffect, useState } from 'react';
import { View, Platform, KeyboardAvoidingView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useHeaderHeight } from '@react-navigation/elements';
import { Stack, useLocalSearchParams } from 'expo-router';
import { getAuth } from 'firebase/auth';
import { FirebaseRuntimeProvider, useFirebaseRuntime } from '@/runtimes/firebase-runtime';
import { subscribeChatTitle } from '@/lib/chat-rtdb';

// Fallback while the title loads or for a chat that has none yet.
const DEFAULT_HEADER_TITLE = 'Chat';
// Keep a long title from colliding with the back button / running off-screen.
const HEADER_TITLE_MAX_WIDTH = 260;

function ChatScreenContent() {
  const { messages, isRunning, sendMessage, retryMessage } = useFirebaseRuntime();
  const insets = useSafeAreaInsets();
  const headerHeight = useHeaderHeight();

  const handleReloadMessage = async (messageId: string) => {
    await retryMessage(messageId);
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
  const [title, setTitle] = useState(DEFAULT_HEADER_TITLE);

  // Mirror the chat's title into the header, live — so a title that's still
  // being auto-generated updates here the moment it lands, matching the list.
  useEffect(() => {
    const uid = getAuth().currentUser?.uid;
    if (!uid || !id) return;
    return subscribeChatTitle(uid, id, (next) => setTitle(next.trim() || DEFAULT_HEADER_TITLE));
  }, [id]);

  if (!id) return null;

  return (
    <FirebaseRuntimeProvider chatId={id}>
      <Stack.Screen
        options={{
          headerTitle: () => (
            <CText variant="lead" bold numberOfLines={1} style={{ maxWidth: HEADER_TITLE_MAX_WIDTH }}>
              {title}
            </CText>
          ),
        }}
      />
      <ChatScreenContent />
    </FirebaseRuntimeProvider>
  );
}
