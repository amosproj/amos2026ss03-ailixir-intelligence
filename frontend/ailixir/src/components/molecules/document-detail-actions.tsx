import type { DocumentStatus } from '@/hooks/useDocuments';
import type { ExtractionResponse } from '@/hooks/useDocumentExtraction';

import { CButton, CText } from '@/components/atoms';
import { ActionPair } from '@/components/molecules';
import { OcrTextCard } from '@/components/organisms';
import { BookUp2, ImageDown } from '@tamagui/lucide-icons-2';
import React from 'react';
import { ScrollView, YStack } from 'tamagui';

const processingStepLabels: Record<string, string> = {
  downloading: 'downloading from storage',
  ocr: 'OCR extraction',
  saving_extraction: 'saving extraction record',
  building_graph: 'building knowledge graph',
  exporting_cypher: 'exporting Cypher script',
};

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

      {ocrTextEnabled && <OcrTextCard extraction={extraction} isLoading={extractionIsLoading} isError={extractionIsError} />}
    </YStack>
  );
}

function FailureCard({ processingStep, error }: { processingStep?: string | null; error?: string | null }) {
  const stepLabel = processingStep ? (processingStepLabels[processingStep] ?? processingStep) : null;
  return (
    <YStack gap={10} bg="$red1" p={16} borderWidth={1} borderColor="$red6" style={{ borderRadius: 16 }}>
      <YStack gap={4}>
        <CText variant="h2" color="$red11">
          Extraction failed
        </CText>
        {stepLabel && (
          <CText variant="caption" color="$red11">
            Failed during {stepLabel}.
          </CText>
        )}
      </YStack>

      {error ? (
        <ScrollView style={{ maxHeight: 200, borderRadius: 10 }} bg="$red2" p={10} showsVerticalScrollIndicator>
          <CText
            variant="caption"
            color="$red12"
            selectable
            style={{
              fontFamily: 'Menlo',
              fontVariant: ['tabular-nums'],
              lineHeight: 18,
            }}>
            {error}
          </CText>
        </ScrollView>
      ) : (
        <CText variant="caption" color="$red11">
          The worker did not record an error message. Re-uploading the document is the easiest next step.
        </CText>
      )}

      <CText variant="caption" color="$red11">
        Try re-uploading the document. If it keeps failing, share the error above with the team.
      </CText>
    </YStack>
  );
}
