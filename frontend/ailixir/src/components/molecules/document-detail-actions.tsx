import type { DocumentStatus } from '@/hooks/useDocuments';
import type { ExtractionResponse } from '@/hooks/useDocumentExtraction';

import { CButton } from '@/components/atoms';
import { ActionPair, FailureCard } from '@/components/molecules';
import { DocumentNarrativeCard, OcrTextCard } from '@/components/organisms';
import { BookUp2, ImageDown } from '@tamagui/lucide-icons-2';
import React from 'react';
import { YStack } from 'tamagui';

type DocumentDetailActionsProps = {
  status: DocumentStatus;
  onStartExtraction: () => void;
  onDownloadGraph: () => void;
  error?: string | null;
  processingStep?: string | null;
  cypherDownloadUrl?: string | null;
  ocrTextEnabled?: boolean;
  extraction?: ExtractionResponse | undefined;
  extractionIsLoading?: boolean;
  extractionIsError?: boolean;
  isStartingExtraction?: boolean;
};

export function DocumentDetailActions({
  status,
  onStartExtraction,
  onDownloadGraph,
  error,
  processingStep,
  cypherDownloadUrl,
  ocrTextEnabled = false,
  extraction,
  extractionIsLoading = false,
  extractionIsError = false,
  isStartingExtraction = false,
}: DocumentDetailActionsProps) {
  // Show the narrative card whenever the document has reached `extracted` (the
  // hook only fetches in that state). The card auto-hides internally when
  // there's no `episode_body` to render — true for legacy OCR-pipeline
  // extractions. So users on either pipeline see the right thing without an
  // explicit pipeline check here.
  const narrativeVisible = status === 'extracted';

  return (
    <YStack gap={20}>
      {status === 'failed' && <FailureCard processingStep={processingStep} error={error} />}

      <ActionPair
        leftAction={
          status === 'pending_upload' ? (
            <CButton icon={BookUp2} emphasis="low" onPress={onStartExtraction} disabled={isStartingExtraction}>
              {isStartingExtraction ? 'Starting...' : 'Start extraction'}
            </CButton>
          ) : null
        }
        rightAction={
          cypherDownloadUrl ? (
            <CButton icon={ImageDown} emphasis="high" onPress={onDownloadGraph}>
              Download graph
            </CButton>
          ) : null
        }
      />

      {narrativeVisible && <DocumentNarrativeCard extraction={extraction} isLoading={extractionIsLoading} isError={extractionIsError} />}

      {ocrTextEnabled && <OcrTextCard extraction={extraction} isLoading={extractionIsLoading} isError={extractionIsError} />}
    </YStack>
  );
}
