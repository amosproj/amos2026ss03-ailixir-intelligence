import apiClient from '@/lib/axios';

export const deleteDoc = async (documentId: string): Promise<void> => {
  try {
    await apiClient.delete(`/documents/${documentId}`);
  } catch (error) {
    console.error(`Failed to delete document ${documentId}:`, error);
    throw error;
  }
};
