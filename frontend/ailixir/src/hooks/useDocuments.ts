import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/axios';

export type DocumentStatus = 'pending_upload' | 'uploaded' | 'processing' | 'extracted' | 'failed';

export interface DocumentListItem {
  document_id: string;
  status: DocumentStatus;
  domain: string;
  title: string;
  file_count: number;
  total_bytes: number;
  created_at: string;
  updated_at: string;
  finalized_at: string | null;
  thumbnail_url: string | null;
  thumbnail_expires_at: string | null;
}

export interface DocumentsResponse {
  documents: DocumentListItem[];
  next_cursor: string | null;
}

export interface DocumentsQueryParams {
  limit?: number;
  cursor?: string | null;
  domain?: string | null;
  status?: DocumentStatus | null;
}

export interface DocumentsValidationErrorDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
  input: string;
  ctx?: Record<string, unknown>;
}

export interface DocumentsValidationErrorResponse {
  detail: DocumentsValidationErrorDetail[];
}

const fetchDocuments = async (params: DocumentsQueryParams): Promise<DocumentsResponse> => {
  const response = await apiClient.get('/documents', { params });
  return response.data;
};

export function useDocuments(params: DocumentsQueryParams = {}, reloadTillExtracted = false) {
  return useQuery({
    queryKey: ['documents', params, reloadTillExtracted],
    queryFn: () => fetchDocuments(params),
    refetchInterval: (query) => {
      if (!reloadTillExtracted) {
        return false;
      }

      const shouldNotReload = query.state.data?.documents?.every((doc) => doc.status === 'extracted' || doc.status === 'failed');

      if (shouldNotReload) {
        return false; // Stop refetching once extracted or failed
      }

      return 3000; // Refetch every 3 seconds until extracted
    },
  });
}