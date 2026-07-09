import { CButton, CText } from '@/components/atoms';
import { DeleteButton, DocumentDetailActions, DocumentPagesThumbnails } from '@/components/molecules';
import { useDocument } from '@/hooks/useDocument';
import { useDocumentExtraction } from '@/hooks/useDocumentExtraction';
import { useFinalizeDocument } from '@/hooks/useFinalizeDocument';
import { showOcrTextAtom } from '@/state/debug';
import { formatDate, formatSize } from '@/utils/format';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { ChevronLeft, File, Trash2 } from '@tamagui/lucide-icons-2';
import { useAtomValue } from 'jotai';
import React, { useCallback } from 'react';
import { Alert } from 'react-native';
import { ScrollView, XStack, YStack } from 'tamagui';

const statusLabels = {
  pending_upload: 'Pending upload',
  uploaded: 'Uploaded',
  processing: 'Processing',
  extracted: 'Extracted',
  failed: 'Failed',
} as const;

const statusStyles = {
  pending_upload: { backgroundColor: '$yellow2', color: '$yellow11' },
  uploaded: { backgroundColor: '$blue2', color: '$blue11' },
  processing: { backgroundColor: '$orange2', color: '$orange11' },
  extracted: { backgroundColor: '$green2', color: '$green11' },
  failed: { backgroundColor: '$red2', color: '$red11' },
} as const;

function DetailRow({ label, value }: { label: string; value?: string }) {
  if (!value) {
    return null;
  }

  return (
    <YStack gap={4} width="48%">
      <CText variant="caption" color="$accent1">
        {label}
      </CText>
      <CText variant="body" bold color="$black5">
        {value}
      </CText>
    </YStack>
  );
}

export default function DocumentScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const { data: document, isLoading, isError } = useDocument(params.id, true);

  // The extraction fetch powers TWO cards now:
  //   - DocumentNarrativeCard: shown whenever an extraction exists (always
  //     fetched on status='extracted', no debug toggle required).
  //   - OcrTextCard: gated behind the Settings debug toggle.
  //
  // The hook is gated on `status === 'extracted'` rather than the debug
  // toggle so the narrative card has data to render. The card itself
  // auto-hides if `episode_body` is absent (legacy OCR records), so
  // unconditional fetching is safe and behavior-neutral for legacy docs.
  const showOcrText = useAtomValue(showOcrTextAtom);
  const documentIsExtracted = document?.status === 'extracted';
  const ocrTextEnabled = showOcrText && documentIsExtracted;
  const { data: extraction, isLoading: extractionIsLoading, isError: extractionIsError } = useDocumentExtraction(params.id, documentIsExtracted);

  const { mutateAsync: finalizeDocument, isPending: isFinalizing } = useFinalizeDocument();

  const handleStartExtraction = useCallback(async () => {
    if (!document || document.status !== 'pending_upload') return;
    try {
      await finalizeDocument({ documentId: document.document_id });
    } catch {
      Alert.alert('Extraction failed to start', 'Could not start the extraction pipeline. Please try again.');
    }
  }, [document, finalizeDocument]);

  if (isLoading) {
    return (
      <YStack flex={1} justify="center" items="center" px={24} bg="$background">
        <CText variant="caption">Loading document...</CText>
      </YStack>
    );
  }

  if (isError || !document) {
    return (
      <YStack flex={1} justify="center" items="center" px={24} bg="$background">
        <CText variant="h2" color="$color11">
          Document not found
        </CText>
        <CText variant="caption" style={{ textAlign: 'center' }}>
          The requested document is not available.
        </CText>
        <CButton icon={ChevronLeft} onPress={() => router.back()} mt={16}>
          Back
        </CButton>
      </YStack>
    );
  }

  const uploadedDate = formatDate(document.created_at);
  const sizeLabel = formatSize(document.total_bytes);
  const fileLabel = document.file_count > 1 ? `${document.file_count} files` : document.files[0]?.file_name;

  return (
    <ScrollView flex={1} showsVerticalScrollIndicator={false}>
      <YStack gap={20} px={16} pt={16} pb={32}>
        <YStack gap={16} bg="$accent12" p={16}>
          <XStack items="center" gap={12}>
            <File size={24} color="$color11" />
            <YStack gap={4} flex={1}>
              <CText variant="caption" color="$accent1">
                Status
              </CText>
              <XStack px={10} py={4} bg={statusStyles[document.status].backgroundColor} style={{ borderRadius: 999, alignSelf: 'flex-start', flexShrink: 0, alignItems: 'center' }}>
                <CText variant="caption" color={statusStyles[document.status].color}>
                  {statusLabels[document.status]}
                </CText>
              </XStack>
            </YStack>
            <DeleteButton documentId={document.document_id} disabled={document.status === 'processing'} onSuccess={() => router.back()} circular>
              <Trash2 size={20} color="$red10" />
            </DeleteButton>
          </XStack>

          <XStack flexWrap="wrap" justify="space-between" gap={16}>
            <DetailRow label="Filename" value={fileLabel} />
            <DetailRow label="Size" value={sizeLabel} />
            <DetailRow label="Uploaded" value={uploadedDate} />
          </XStack>
        </YStack>

        <DocumentDetailActions
          status={document.status}
          onStartExtraction={handleStartExtraction}
          error={document.error}
          processingStep={document.processing_step}
          ocrTextEnabled={ocrTextEnabled}
          extraction={extraction}
          extractionIsLoading={extractionIsLoading}
          extractionIsError={extractionIsError}
          isStartingExtraction={isFinalizing}
        />

        <YStack gap={12}>
          <CText variant="h2" color="$color11">
            Pages
          </CText>
          <DocumentPagesThumbnails files={document.files} />
        </YStack>
      </YStack>
    </ScrollView>
  );
}
