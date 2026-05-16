import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useState } from 'react';

export interface SelectedFile {
  uri: string;
  name: string;
  type: string;
}

const uploadFileApi = async (file: SelectedFile, onProgress: (progress: number) => void) => {
  const formData = new FormData();

  formData.append('file', {
    uri: file.uri,
    name: file.name || 'upload_file',
    type: file.type,
  } as any);

  const response = await axios.post('https://ailixir-backend-5mg2ellzaa-ue.a.run.app/document/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent) => {
      const total = progressEvent.total ?? 1;
      const percentCompleted = Math.round((progressEvent.loaded * 100) / total);
      onProgress(percentCompleted);
    },
  });

  return response.data;
};

export function useFileUpload() {
  const queryClient = useQueryClient();
  const [uploadProgress, setUploadProgress] = useState<number>(0);

  const mutation = useMutation({
    mutationFn: (file: SelectedFile) => uploadFileApi(file, setUploadProgress),
    onSuccess: (data) => {
      // invalidating cache after successfull upload
      queryClient.invalidateQueries({ queryKey: ['files'] });
      setUploadProgress(0);
    },
    onError: (error) => {
      console.error('Upload Error:', error);
      setUploadProgress(0);
    },
  });

  return {
    uploadFile: mutation.mutate,
    uploadFileAsync: mutation.mutateAsync,
    isUploading: mutation.isPending,
    isSuccess: mutation.isSuccess,
    isError: mutation.isError,
    error: mutation.error,
    uploadProgress,
    reset: mutation.reset,
  };
}
