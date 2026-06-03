'use client';

import { CButton, CInput } from '@/components/atoms';
import React, { useState, useRef } from 'react';
import { View } from 'react-native';
import { TamaguiElement } from 'tamagui';
import { Send, Mic, AudioWaveform } from '@tamagui/lucide-icons-2';
import { LinearGradient } from 'expo-linear-gradient';

export interface ChatInputProps {
  onSendMessage: (message: string) => void;
  onStartVoiceMode: () => void;
  placeholder?: string;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, onStartVoiceMode, placeholder = 'Type a message...' }) => {
  const [message, setMessage] = useState('');
  const inputRef = useRef<TamaguiElement>(null);

  const handleSend = () => {
    if (message.trim()) {
      onSendMessage?.(message);
      setMessage('');
      inputRef.current?.focus();
    }
  };

  const onPressTextToSpeech = () => {
    // TODO: Implement text-to-speech logic (e.g., call API to convert text to speech)
    alert('Text-to-speech not available');
  };

  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'flex-end',
        backgroundColor: '#F4F4F4',
        borderRadius: 8,
        paddingHorizontal: 12,
        paddingVertical: 8,
        gap: 4,
      }}>
      <CInput
        ref={inputRef}
        value={message}
        onChangeText={setMessage}
        placeholder={placeholder}
        theme="bright"
        multiline
        numberOfLines={3}
        style={{
          flex: 1,
          maxHeight: 100,
          backgroundColor: 'transparent',
          paddingHorizontal: 0,
          paddingVertical: 0,
        }}
      />
      <CButton onPress={onPressTextToSpeech} icon={Mic} accessibilityLabel="Text-to-speech" />
      {message.trim() ? (
        <CButton circular icon={Send} onPress={handleSend} accessibilityLabel="Send message" />
      ) : (
        <LinearGradient colors={['#8847EF', '#FF1493']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ borderRadius: 999 }}>
          <CButton onPress={onStartVoiceMode} circular icon={AudioWaveform} tone="accent" accessibilityLabel="Start voice mode" />
        </LinearGradient>
      )}
    </View>
  );
};
