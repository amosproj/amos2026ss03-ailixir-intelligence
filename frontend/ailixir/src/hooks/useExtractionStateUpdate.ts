import { Document, DocumentExtractionStatus } from '@/interfaces/document';
import apiClient from '@/lib/axios';
import { documentsAtom, updateDocumentStatusAtom } from '@/lib/documentAtoms';
import { useQuery } from '@tanstack/react-query';
import { useAtomValue, useSetAtom } from 'jotai';

const RELOAD_TIMEOUT = 3_000;

const singleQueryFn = async (document: Document): Promise<{ status: DocumentExtractionStatus }> => {
  if (document.status !== 'extracting') {
    return { status: document.status };
  }

  try {
    const resp = await apiClient.get(`/documents/${document.id}`);
    return resp.data as { status: DocumentExtractionStatus };
  } catch (error) {
    console.log('Error fetching document data: ', error);
    return { status: 'extracting' };
  }
};

export const useExtractionStateUpdate = (documentId?: string) => {
  const docsSrc = useAtomValue(documentsAtom);

  const documents = !documentId ? docsSrc : ([docsSrc.find((entry) => entry.id === documentId)].filter(Boolean) as unknown as Document[]);

  const updateDocumentStatus = useSetAtom(updateDocumentStatusAtom);

  useQuery<{ status: string }[]>({
    queryKey: ['documentExtraction', ...documents.map((doc) => doc.id)],
    queryFn: () => {
      // Placeholder for query function
      return Promise.all(documents.map(singleQueryFn));
    },
    refetchInterval: (query) => {
      let shouldRefetch = false;

      for (let i = 0; i < documents.length; i++) {
        const document = documents[i];
        const docRespData = query.state?.data?.[i]?.status;

        if (!docRespData) continue;

        const extractionSuccessful = docRespData === 'extracted';
        const extractionFailed = docRespData === 'failed';

        if (extractionSuccessful) updateDocumentStatus({ documentId: document.id, status: 'extracted' });

        if (extractionFailed) updateDocumentStatus({ documentId: document.id, status: 'failed' });

        if (extractionSuccessful || extractionFailed) continue;

        shouldRefetch = true;
      }

      return shouldRefetch ? RELOAD_TIMEOUT : false;
    },
  });
};
