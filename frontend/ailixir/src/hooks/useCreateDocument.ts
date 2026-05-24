import { useMutation } from '@tanstack/react-query';
import apiClient from '@/lib/axios';

export interface CreateDocumentFileInput {
  file_name: string;
  content_type: string;
  size_bytes: number;
}

export interface CreateDocumentInput {
  domain: string;
  title: string;
  files: CreateDocumentFileInput[];
}

export interface CreateDocumentFileUpload {
  file_id: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  upload_method: 'PUT';
  upload_url: string;
  upload_headers?: Record<string, string>;
  upload_expires_at: string;
}

export interface CreateDocumentResponse {
  document_id: string;
  status: 'pending_upload';
  domain: string;
  title: string;
  file_count: number;
  total_bytes: number;
  files: CreateDocumentFileUpload[];
  created_at: string;
}

export interface CreateDocumentValidationErrorDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
  input: string;
  ctx?: Record<string, unknown>;
}

export interface CreateDocumentValidationErrorResponse {
  detail: CreateDocumentValidationErrorDetail[];
}

const createDocument = async (payload: CreateDocumentInput): Promise<CreateDocumentResponse> => {
  const response = await apiClient.post('/documents', payload);
  return response.data;
};

export function useCreateDocument() {
  return useMutation({
    mutationFn: createDocument,
  });
}
