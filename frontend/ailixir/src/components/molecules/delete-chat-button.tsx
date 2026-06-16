import React, { useCallback } from 'react';
import { Alert } from 'react-native';
import { getAuth } from 'firebase/auth';

import { CButton, type CButtonProps } from '@/components/atoms';
import { deleteChat } from '@/lib/chat-rtdb';

export type DeleteChatButtonProps = Omit<CButtonProps, 'onPress'> & {
  chatId: string;
  onSuccess?: () => void;
};

export function DeleteChatButton({ chatId, onSuccess, ...buttonProps }: DeleteChatButtonProps) {
  const handleDelete = useCallback(() => {
    Alert.alert('Delete Chat', 'Are you sure you want to delete this chat?', [
      {
        text: 'Cancel',
        onPress: () => {},
        style: 'cancel',
      },
      {
        text: 'Delete',
        onPress: async () => {
          const uid = getAuth().currentUser?.uid;
          if (!uid) {
            Alert.alert('Error', 'You must be logged in to delete chats.');
            return;
          }

          try {
            await deleteChat(uid, chatId);
            Alert.alert('Success', 'Chat deleted successfully.');
            onSuccess?.();
          } catch (error) {
            console.error('Delete chat error:', error);
            Alert.alert('Error', 'Failed to delete chat. Please try again.');
          }
        },
        style: 'destructive',
      },
    ]);
  }, [chatId, onSuccess]);

  return <CButton onPress={handleDelete} {...buttonProps} />;
}
