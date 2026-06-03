import type { DocumentStatus } from '@/hooks/useDocuments';

import { CButton } from '@/components/atoms';
import { ActionPair } from '@/components/molecules';
import { BookUp2, ImageDown } from '@tamagui/lucide-icons-2';

type DocumentDetailActionsProps = {
  status: DocumentStatus;
  onStartExtraction: () => void;
  onDownloadGraph: () => void;
};

export function DocumentDetailActions({ status, onStartExtraction, onDownloadGraph }: DocumentDetailActionsProps) {
  return (
    <ActionPair
      leftAction={
        status === 'uploaded' ? (
          <CButton icon={BookUp2} emphasis="low" onPress={onStartExtraction}>
            Start extraction
          </CButton>
        ) : null
      }
      rightAction={
        <CButton icon={ImageDown} emphasis="high" onPress={onDownloadGraph}>
          Download graph
        </CButton>
      }
    />
  );
}
