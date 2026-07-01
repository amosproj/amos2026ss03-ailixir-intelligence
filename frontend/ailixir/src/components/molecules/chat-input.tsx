'use client';

import { CButton, CInput, CText } from '@/components/atoms';
import React, { useState, useRef } from 'react';
import { TouchableOpacity, View } from 'react-native';
import { TamaguiElement } from 'tamagui';
import { Send, Mic, AudioWaveform } from '@tamagui/lucide-icons-2';
import { LinearGradient } from 'expo-linear-gradient';
import { Orb } from '@/components/molecules';

export interface ChatInputProps {
  onSendMessage: (message: string) => void;
  onStartVoiceMode: () => void;
  onStopVoiceMode?: () => void;
  isVoiceModeActive?: boolean;
  placeholder?: string;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, onStartVoiceMode, onStopVoiceMode, isVoiceModeActive = false, placeholder = 'Type a message...' }) => {
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

  if (isVoiceModeActive) {
    return (
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          backgroundColor: '#F4F4F4',
          borderRadius: 8,
          paddingHorizontal: 12,
          paddingVertical: 8,
          gap: 12,
        }}>
        <View style={{ flex: 1, alignItems: 'center' }}>
          <Orb agentState="listening" />
        </View>
        <TouchableOpacity onPress={onStopVoiceMode} accessibilityLabel="Close voice mode" style={{ paddingVertical: 8 }}>
          <CText variant="body" bold>
            Close
          </CText>
        </TouchableOpacity>
      </View>
    );
  }

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
