import { atom } from 'jotai';

import { MOCK_DOCUMENTS } from '@/constants/mock-documents';
import type { Document, DocumentExtractionStatus } from '@/interfaces/document';

export const documentsAtom = atom<Document[]>(MOCK_DOCUMENTS);

export const updateDocumentStatusAtom = atom(null, (get, set, { documentId, status }: { documentId: string; status: DocumentExtractionStatus }) => {
  const updatedDocuments = get(documentsAtom).map((document) => (document.id === documentId ? { ...document, status } : document));

  set(documentsAtom, updatedDocuments);
});
