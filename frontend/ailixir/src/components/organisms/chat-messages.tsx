import React, { useEffect, useRef } from 'react';
import { ScrollView, View } from 'react-native';
import { CText } from '@/components/atoms';
import { ChatUserMessage } from '@/components/molecules/chat-user-message';
import { ChatAssistantMessage } from '@/components/molecules/chat-assistant-message';

export interface ChatMessage {
  id: string;
  text: string;
  timestamp: Date;
  role: 'user' | 'assistant';
}

export interface ChatMessagesProps {
  messages: ChatMessage[];
  onReloadMessage?: (messageId: string) => void;
}

export const ChatMessages: React.FC<ChatMessagesProps> = ({ messages, onReloadMessage }) => {
  const scrollViewRef = useRef<ScrollView>(null);

  useEffect(() => {
    // Auto-scroll to bottom when new messages arrive
    scrollViewRef.current?.scrollToEnd({ animated: true });
  }, [messages]);

  const renderMessage = (msg: ChatMessage) => {
    if (msg.role === 'user') {
      return <ChatUserMessage key={msg.id} text={msg.text} />;
    }

    if (msg.role === 'assistant') {
      return <ChatAssistantMessage key={msg.id} text={msg.text} onReload={() => onReloadMessage?.(msg.id)} />;
    }
  };

  return (
    <ScrollView
      ref={scrollViewRef}
      contentContainerStyle={{
        padding: 16,
        gap: 8,
      }}
      style={{
        flex: 1,
      }}>
      {messages.length === 0 ? (
        <View style={{ justifyContent: 'center', alignItems: 'center', flex: 1 }}>
          <CText variant="body">Start a chat with your AI assistant!</CText>
        </View>
      ) : (
        messages.map(renderMessage)
      )}
    </ScrollView>
  );
};
