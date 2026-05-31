'use client';

import { ChatMessages, ChatMessage } from '@/components/organisms/chat-messages';
import { ChatInput } from '@/components/molecules';
import { CText } from '@/components/atoms';
import React, { useState } from 'react';
import { View, Platform, KeyboardAvoidingView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useHeaderHeight } from '@react-navigation/elements';

export default function ChatScreen() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    // {
    //   id: '1',
    //   text: 'Hello! This is a sample message.',
    //   timestamp: new Date(),
    //   role: 'user',
    // },
    // {
    //   id: '2',
    //   text: 'Hello, this is a sample response.',
    //   timestamp: new Date(),
    //   role: 'assistant',
    // },
  ]);
  const insets = useSafeAreaInsets();
  const headerHeight = useHeaderHeight();

  const handleSendMessage = (text: string) => {
    const newMessage: ChatMessage = {
      id: Date.now().toString(),
      text,
      timestamp: new Date(),
      role: 'user',
    };
    setMessages((prev) => [...prev, newMessage]);

    // TODO: Call API to get assistant response and add to messages

    setMessages((prev) => [
      ...prev,
      {
        id: (Date.now() + 1).toString(),
        text: 'This is a placeholder response from the assistant.',
        timestamp: new Date(),
        role: 'assistant',
      },
    ]);
  };

  const handleReloadMessage = (messageId: string) => {
    // TODO: Implement reload logic (e.g., call API to regenerate response)
    alert('Reload not available');
    console.log('Reload message:', messageId);
  };

  return (
    <KeyboardAvoidingView
      keyboardVerticalOffset={headerHeight}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={{
        flex: 1,
      }}>
      <View
        style={{
          flex: 1,
          backgroundColor: '#fff',
        }}>
        {/* Chat messages area */}
        <ChatMessages messages={messages} onReloadMessage={handleReloadMessage} />

        {/* Input area with keyboard spacing */}
        <View
          style={{
            paddingLeft: 16,
            paddingRight: 16,
            paddingTop: 12,
            paddingBottom: Platform.OS === 'web' ? 12 : Math.max(insets.bottom, 12),
            borderTopWidth: 1,
            borderTopColor: '#e0e0e0',
          }}>
          <ChatInput onStartVoiceMode={() => alert('Voice mode not available')} onSendMessage={handleSendMessage} />
          <CText variant="caption" style={{ marginTop: 8, textAlign: 'center' }}>
            AI can make mistakes.
          </CText>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}
