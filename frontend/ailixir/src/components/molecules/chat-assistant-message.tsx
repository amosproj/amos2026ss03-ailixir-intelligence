import { CText, CButton } from '@/components/atoms';
import React, { useState } from 'react';
import { View } from 'react-native';
import { Copy, RotateCcw } from '@tamagui/lucide-icons-2';
import * as Clipboard from 'expo-clipboard';

interface ChatAssistantMessageProps {
  text: string;
  onReload?: () => void;
}

export const ChatAssistantMessage: React.FC<ChatAssistantMessageProps> = ({ text, onReload }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await Clipboard.setStringAsync(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <View
      style={{
        alignSelf: 'flex-start',
        maxWidth: '80%',
        borderRadius: 8,
        padding: 12,
      }}>
      <CText variant="body">{text}</CText>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'flex-start',
        }}>
        {/* @ts-ignore "color" not recognised as prop */}
        <CButton icon={RotateCcw} onPress={onReload} accessibilityLabel="Reload message" color="#666" size={30}>
          <CText variant="caption">Reload</CText>
        </CButton>

        {/* @ts-ignore "color" not recognised as prop */}
        <CButton disabled={copied} opacity={copied ? 0.5 : 1} icon={Copy} onPress={handleCopy} accessibilityLabel="Copy message" color="#666" size={30}>
          <CText variant="caption">{copied ? 'Copied' : 'Copy'}</CText>
        </CButton>
      </View>
    </View>
  );
};
