import { useMutation } from '@tanstack/react-query';
import apiClient from '@/lib/axios';

export interface FinalizeDocumentInput {
  documentId: string;
}

export interface FinalizeDocumentResponse {
  document_id: string;
  status: 'pending_upload';
  domain: string;
  title: string;
  file_count: number;
  total_bytes: number;
  files: {
    file_id: string;
    file_name: string;
    content_type: string;
    size_bytes: number;
    upload_completed_at: string;
    download_url: string;
    download_expires_at: string;
  }[];
  created_at: string;
  updated_at: string;
  finalized_at: string;
}

export interface FinalizeDocumentValidationErrorDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
  input: string;
  ctx?: Record<string, unknown>;
}

export interface FinalizeDocumentValidationErrorResponse {
  detail: FinalizeDocumentValidationErrorDetail[];
}

const finalizeDocument = async (payload: FinalizeDocumentInput): Promise<FinalizeDocumentResponse> => {
  const response = await apiClient.post(`/documents/${payload.documentId}/finalize`);
  return response.data;
};

export function useFinalizeDocument() {
  return useMutation({
    mutationFn: finalizeDocument,
  });
}
