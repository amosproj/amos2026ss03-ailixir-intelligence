/**
 * Fetch the OCR extraction for a document (structured fields + raw OCR text).
 *
 * Backend contract: GET /documents/{documentId}/extraction
 *   200  → ExtractionResponse
 *   404  → DOCUMENT_NOT_FOUND   (doesn't exist or not owned by caller)
 *   404  → EXTRACTION_NOT_FOUND (status=extracted but no record — pipeline bug)
 *   409  → DOCUMENT_NOT_EXTRACTED (still processing — keep polling /documents/{id})
 *
 * The hook is `enabled`-gated by the caller (typically: debug toggle ON
 * AND document.status === 'extracted'). With `staleTime: Infinity` the
 * extraction is fetched once per session — extractions are immutable
 * once written, so refetching is wasted bandwidth.
 */

import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/axios';

export interface ExtractionResponse {
  doc_id: string;
  document_type: string;
  // ── Legacy OCR fields (populated only by the Document-AI pipeline) ────────
  // Older extraction records still carry these. The new Gemini-multimodal
  // pipeline leaves them null. The OCR debug card uses them when present.
  confidence_score: number | null;
  extracted_fields: Record<string, unknown>;
  raw_text: string | null;
  raw_text_chars: number | null;
  raw_text_truncated: boolean | null;
  // ── New LLM fields (populated only by the Gemini-multimodal pipeline) ────
  // `episode_body` is the rich clinical narrative shown on the Document
  // Narrative card. `document_purpose` and `document_date` drive the chips
  // on that card's header.
  document_purpose: string | null;
  document_date: string | null;
  episode_body: string | null;
  extracted_at: string;
}

const fetchExtraction = async (documentId: string): Promise<ExtractionResponse> => {
  const response = await apiClient.get(`/documents/${documentId}/extraction`);
  return response.data;
};

export function useDocumentExtraction(documentId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['document-extraction', documentId],
    queryFn: () => fetchExtraction(documentId ?? ''),
    enabled: Boolean(documentId) && enabled,
    staleTime: Infinity,
    // Don't retry on 409 (still processing) or 4xx ownership errors — the
    // caller's `enabled` flag is the right gate for transitions, and retry
    // would mask real errors. React Query's default retries 3x on network
    // errors only, which is fine.
    retry: (failureCount, error: unknown) => {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status && status >= 400 && status < 500) {
        return false;
      }
      return failureCount < 2;
    },
  });
}
