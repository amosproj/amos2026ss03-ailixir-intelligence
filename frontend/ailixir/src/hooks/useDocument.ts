import { useQuery } from '@tanstack/react-query';
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
  // Worker-written fields. Populated once the extraction pipeline has
  // produced a Cypher dump and uploaded it to GCS. Both URL and expiry
  // are null when no extraction has been written yet, the user
  // doesn't own the document, or signing failed server-side.
  cypher_gcs_uri?: string | null;
  cypher_download_url?: string | null;
  cypher_download_expires_at?: string | null;
  // Pipeline diagnostics. `processing_step` shows fine-grained progress
  // for in-flight extractions ("downloading", "ocr", "building_graph",
  // "exporting_cypher", "saving_extraction"). When `status === 'failed'`
  // it records the step the worker was on at the moment it raised —
  // useful for telling a Document AI failure from a Graphiti failure.
  processing_step?: string | null;
  // Free-form worker error message when `status === 'failed'`. May
  // contain implementation detail (model names, exception classes). The
  // frontend treats it as opaque diagnostic — display as-is in a
  // monospace card so a user can copy it into a support request.
  error?: string | null;
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
