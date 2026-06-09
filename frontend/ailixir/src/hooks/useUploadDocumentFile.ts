import { useMutation } from '@tanstack/react-query';
// expo-file-system v19 reorganised the API: the new default export uses
// File/Directory classes, while the procedural uploadAsync + upload-type
// enum we want now live under the /legacy subpath. The legacy module is
// the documented, supported way to call binary uploads in v19+ — the
// "modern" API doesn't (yet) cover signed-URL PUTs.
import * as FileSystem from 'expo-file-system/legacy';
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

/**
 * Upload a file from a local URI to a signed PUT URL.
 *
 * The previous implementation used `fetch(uri).then(r => r.blob())` and PUT
 * the blob via axios. That looks correct but is silently broken on React
 * Native: RN's Blob is not the actual file bytes, it's a reference object.
 * When axios serializes the body, it JSON-stringifies the reference into
 * ~175 bytes of `{"_data":{...}}` metadata, which then gets uploaded to GCS
 * instead of the real PDF. Document AI receives 175 bytes labelled as a PDF
 * and returns 500.
 *
 * `FileSystem.uploadAsync` reads the file bytes natively and streams them
 * directly to the URL — no Blob serialization step. This is the Expo-
 * sanctioned way to PUT a binary file to a signed URL.
 */
const uploadDocumentFileApi = async (file: UploadDocumentFileInput, onProgress: (progress: number) => void): Promise<UploadDocumentFileResponse> => {
  // FileSystem.uploadAsync doesn't expose progress events; emit a one-shot
  // start/complete signal so the existing UI hook still works.
  onProgress(1);

  const result = await FileSystem.uploadAsync(file.uploadUrl, file.uri, {
    httpMethod: 'PUT',
    // BINARY_CONTENT: send the file bytes as the raw request body — no
    // multipart wrapping. The signed URL was generated for this exact PUT
    // shape; multipart would invalidate the signature.
    uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
    headers: {
      'Content-Type': file.contentType,
      ...file.uploadHeaders,
    },
  });

  onProgress(100);

  if (result.status >= 200 && result.status < 300) {
    return { status: result.status };
  }

  // GCS returns the actual rejection reason in the body — surface it so a
  // signature/header/size mismatch is debuggable instead of a generic axios
  // error. Truncate to keep logs sane.
  throw new Error(`GCS PUT failed: HTTP ${result.status} ${result.body?.slice(0, 200) ?? ''}`);
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
