import type { DocumentExtractionStatus } from '@/interfaces/document';

type StatusStyle = {
  backgroundColor: '$yellow2' | '$blue2' | '$green2';
  color: '$yellow11' | '$blue11' | '$green11';
};

export const documentExtractionStatusLabels: Record<DocumentExtractionStatus, string> = {
  not_extracted: 'Not extracted',
  extracting: 'Extraction in progress',
  extracted: 'Knowledge extracted',
};

export const documentExtractionStatusStyles: Record<DocumentExtractionStatus, StatusStyle> = {
  not_extracted: { backgroundColor: '$yellow2', color: '$yellow11' },
  extracting: { backgroundColor: '$blue2', color: '$blue11' },
  extracted: { backgroundColor: '$green2', color: '$green11' },
};