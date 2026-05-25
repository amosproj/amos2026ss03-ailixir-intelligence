import apiClient from "@/lib/axios";
import { documentsAtom, updateDocumentStatusAtom } from "@/lib/documentAtoms";
import { useQuery } from "@tanstack/react-query";
import { useAtomValue, useSetAtom } from "jotai";

const RELOAD_TIMEOUT = 3_000;

export const useExtractionStateUpdate = (documentId: string) => {
  const documents = useAtomValue(documentsAtom);
  const document = documents.find((entry) => entry.id === documentId);
  
  const updateDocumentStatus = useSetAtom(updateDocumentStatusAtom);

  // const { data, error } = 
  useQuery({
    queryKey: ['documentExtraction', documentId],
    queryFn: async () => {
      if (!document) {
        return { status: 'failed' };
      }

      if (document.status !== 'extracting') {
        return { status: document.status };
      }

      try {
        const resp = await apiClient.get(`/documents/${documentId}`);
        // console.log("got data: ", resp.data)
        return resp;
      } catch (error) {
        console.log("Error fetching document data: ", error);
        return { status: 'extracting' };
      }
    },
    refetchInterval: (query) => {
      if (!document) return RELOAD_TIMEOUT;
      const docRespData = (query.state?.data as any)?.data as { status: string } | undefined;

      if (!docRespData) return RELOAD_TIMEOUT;

      // console.log(query.state.data);
      // Stop polling once the job finishes
      if (document?.status !== "extracting") return false;

      const extractionSuccessful = docRespData.status === 'extracted';
      const extractionFailed = docRespData.status === 'failed';

      if (document && extractionSuccessful) 
        updateDocumentStatus({ documentId: document.id, status: 'extracted' });

      if (document && extractionFailed) 
        updateDocumentStatus({ documentId: document.id, status: 'failed' });

      if (extractionSuccessful || extractionFailed) return false;
      
      // if (query.state.error) return false;
      
      return RELOAD_TIMEOUT;
    },
  });
}