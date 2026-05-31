import { CText } from '@/components/atoms';
import React from 'react';
import { View } from 'react-native';

interface ChatUserMessageProps {
  text: string;
}

export const ChatUserMessage: React.FC<ChatUserMessageProps> = ({ text }) => {
  return (
    <View
      style={{
        alignSelf: 'flex-end',
        maxWidth: '80%',
        backgroundColor: '#847EF3',
        borderRadius: 8,
        padding: 12,
      }}>
      <CText style={{ color: 'white' }} variant="body">
        {text}
      </CText>
    </View>
  );
};
