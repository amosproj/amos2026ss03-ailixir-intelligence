import { useMutation } from '@tanstack/react-query';
import axios from 'axios';
import { useState } from 'react';

export interface UploadDocumentFileInput {
  uri: string;
  contentType: string;
  uploadUrl: string;
  uploadHeaders?: Record<string, string>;
}

export interface UploadDocumentFileResponse {
  status: number;
}

const uploadDocumentFileApi = async (file: UploadDocumentFileInput, onProgress: (progress: number) => void): Promise<UploadDocumentFileResponse> => {
  const blobResponse = await fetch(file.uri);
  const blob = await blobResponse.blob();

  const response = await axios.put(file.uploadUrl, blob, {
    headers: {
      'Content-Type': file.contentType,
      ...file.uploadHeaders,
    },
    onUploadProgress: (progressEvent) => {
      const total = progressEvent.total ?? 1;
      const percentCompleted = Math.round((progressEvent.loaded * 100) / total);
      onProgress(percentCompleted);
    },
  });

  return { status: response.status };
};

export function useUploadDocumentFile() {
  const [uploadProgress, setUploadProgress] = useState<number>(0);

  const mutation = useMutation({
    mutationFn: (file: UploadDocumentFileInput) => uploadDocumentFileApi(file, setUploadProgress),
    onSuccess: () => {
      setUploadProgress(0);
    },
    onError: (error) => {
      console.error('Upload Error:', error);
      setUploadProgress(0);
    },
  });

  return {
    uploadDocumentFile: mutation.mutate,
    uploadDocumentFileAsync: mutation.mutateAsync,
    isUploading: mutation.isPending,
    isSuccess: mutation.isSuccess,
    isError: mutation.isError,
    error: mutation.error,
    uploadProgress,
    reset: mutation.reset,
  };
}
