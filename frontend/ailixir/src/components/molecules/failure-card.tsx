import { CText } from '@/components/atoms';
import React from 'react';
import { ScrollView, YStack } from 'tamagui';

const processingStepLabels: Record<string, string> = {
  downloading: 'downloading from storage',
  ocr: 'OCR extraction',
  saving_extraction: 'saving extraction record',
  building_graph: 'building knowledge graph',
  exporting_cypher: 'exporting Cypher script',
};

type FailureCardProps = {
  processingStep?: string | null;
  error?: string | null;
};

export function FailureCard({ processingStep, error }: FailureCardProps) {
  const stepLabel = processingStep ? (processingStepLabels[processingStep] ?? processingStep) : null;
  return (
    <YStack gap={10} bg="$red1" p={16} borderWidth={1} borderColor="$red6">
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
        <ScrollView style={{ maxHeight: 200 }} bg="$red2" p={10} showsVerticalScrollIndicator>
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
