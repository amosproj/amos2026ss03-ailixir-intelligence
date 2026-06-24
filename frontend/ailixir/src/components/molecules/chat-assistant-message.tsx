import { CText, CButton } from '@/components/atoms';
import React, { useState } from 'react';
import { View } from 'react-native';
import { Copy, RotateCcw } from '@tamagui/lucide-icons-2';
import * as Clipboard from 'expo-clipboard';

interface ChatAssistantMessageProps {
  text: string;
  onReload: () => void;
}

export const ChatAssistantMessage: React.FC<ChatAssistantMessageProps> = ({ text, onReload }) => {
  const [copied, setCopied] = useState(false);
  const hasContent = text.trim().length > 0;

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
        {hasContent ? (
          <>
            <CButton icon={RotateCcw} onPress={onReload} accessibilityLabel="Reload message" tone="muted" size={30}>
              <CText variant="caption">Reload</CText>
            </CButton>

            <CButton disabled={copied} opacity={copied ? 0.5 : 1} icon={Copy} onPress={handleCopy} accessibilityLabel="Copy message" tone="muted" size={30}>
              <CText variant="caption">{copied ? 'Copied' : 'Copy'}</CText>
            </CButton>
          </>
        ) : null}
      </View>
    </View>
  );
};
