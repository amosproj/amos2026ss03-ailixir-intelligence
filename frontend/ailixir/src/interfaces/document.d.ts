export type DocumentExtractionStatus = 'failed' | 'extracting' | 'extracted';
export type DocumentDraft = Pick<Document, 'title' | 'size'>;

export interface Document {
  id: string;
  title: string;
  timestamp: string;
  size: string;
  type: string;
  tags: string[];

  // Optional metadata for the document detail view
  fileName?: string;
  status: DocumentExtractionStatus;
  fromDate?: string;
  uploadedDate?: string;
  facilityName?: string;
  // Pages: array of pages with optional thumbnail URIs
  pages?: {
    id: string;
    pageNumber?: number;
    thumbnail?: string;
  }[];
}
