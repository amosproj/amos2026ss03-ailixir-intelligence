import { CButton, type CButtonProps } from '@/components/atoms';
import { deleteDoc } from '@/lib/deleteDoc';
import { useQueryClient } from '@tanstack/react-query';
import React, { useCallback } from 'react';
import { Alert } from 'react-native';

export type DeleteButtonProps = Omit<CButtonProps, 'onPress'> & {
  documentId: string;
  onSuccess?: () => void;
};

export function DeleteButton({ documentId, onSuccess, ...buttonProps }: DeleteButtonProps) {
  const queryClient = useQueryClient();

  const handleDelete = useCallback(async () => {
    Alert.alert('Delete Document', 'Are you sure you want to delete this document?', [
      {
        text: 'Cancel',
        onPress: () => {},
        style: 'cancel',
      },
      {
        text: 'Delete',
        onPress: async () => {
          try {
            await deleteDoc(documentId);
            queryClient.invalidateQueries({ queryKey: ['documents'] });
            Alert.alert('Success', 'Document deleted successfully');
            onSuccess?.();
          } catch (error) {
            console.error('Delete error:', error);
            Alert.alert('Error', 'Failed to delete document. This is probably because the document is currently being processed. Please try again.');
          }
        },
        style: 'destructive',
      },
    ]);
  }, [documentId, onSuccess, queryClient]);

  return <CButton onPress={handleDelete} {...buttonProps} />;
}
