import { useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/lib/axios';
import { DocumentStatus } from '@/hooks/useDocuments';

export interface DocumentFile {
  file_id: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  upload_completed_at: string;
  download_url: string;
  download_expires_at: string;
}

export interface DocumentResponse {
  document_id: string;
  status: DocumentStatus;
  domain: string;
  title: string;
  file_count: number;
  total_bytes: number;
  files: DocumentFile[];
  created_at: string;
  updated_at: string;
  finalized_at: string;
}

export interface DocumentValidationErrorDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
  input: string;
  ctx?: Record<string, unknown>;
}

export interface DocumentValidationErrorResponse {
  detail: DocumentValidationErrorDetail[];
}

const fetchDocument = async (documentId: string): Promise<DocumentResponse> => {
  const response = await apiClient.get(`/documents/${documentId}`);
  return response.data;
};

export function useDocument(documentId?: string, reloadTillExtracted = false) {
  return useQuery({
    queryKey: ['document', documentId, reloadTillExtracted],
    queryFn: () => fetchDocument(documentId ?? ''),
    enabled: Boolean(documentId),
    refetchInterval: (query) => {
      if (!reloadTillExtracted) {
        return false;
      }

      if (!documentId) {
        return false; // Disable refetching
      }

      const extractedStatus = query.state.data?.status;
      if (extractedStatus === 'extracted' || extractedStatus === 'failed') {
        return false; // Stop refetching once extracted or failed
      }

      return 3000; // Refetch every second until extracted
    },
  });
}
