import { CButton, CText } from '@/components/atoms';
import { DeleteButton, DocumentPageThumbnail } from '@/components/molecules';
import { OcrTextCard } from '@/components/organisms';
import { useDocument } from '@/hooks/useDocument';
import { useDocumentExtraction } from '@/hooks/useDocumentExtraction';
import { showOcrTextAtom } from '@/state/debug';
import { formatDate, formatSize } from '@/utils/format';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system/legacy';
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

// Human-friendly labels for the worker's free-form processing_step values.
// New steps added on the worker side will display as the raw key until
// added here — a deliberate fallback rather than swallowing them with
// a generic "unknown step".
const processingStepLabels: Record<string, string> = {
  downloading: 'downloading from storage',
  ocr: 'OCR extraction',
  saving_extraction: 'saving extraction record',
  building_graph: 'building knowledge graph',
  exporting_cypher: 'exporting Cypher script',
};

/** Failure detail card. Shown on `status === 'failed'`. */
function FailureCard({ processingStep, error }: { processingStep?: string | null; error?: string | null }) {
  // Worker-side errors are often a single line ("Rate limit exceeded.")
  // but can be a long Document AI / gRPC message. Cap the visible height
  // so a long error doesn't push the rest of the screen below the fold,
  // and let the user scroll the body to read the full text.
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

export default function DocumentScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const { data: document, isLoading, isError } = useDocument(params.id, true);

  // Debug-only OCR text fetch. Gated behind (a) the user's Settings toggle
  // and (b) status === 'extracted' so we don't hammer the API while the
  // worker is still mid-pipeline. The hook short-circuits when either gate
  // is false; no request is sent.
  const showOcrText = useAtomValue(showOcrTextAtom);
  const ocrTextEnabled = showOcrText && document?.status === 'extracted';
  const { data: extraction, isLoading: extractionIsLoading, isError: extractionIsError } = useDocumentExtraction(params.id, ocrTextEnabled);

  // Download the Cypher graph script the worker produced for this document.
  //
  // Flow:
  //   1. Backend serves the document with a short-lived v4 signed GET URL
  //      (`cypher_download_url`). Its expiry sits on the same response so
  //      we could re-fetch the document if it lapsed mid-session.
  //   2. We stream the URL to a per-document file in the app's cache
  //      directory (`<cacheDir>/<doc_id>_graph.cypher`). The destination
  //      lives inside our sandbox so iOS' share-sheet can hand it off to
  //      other apps without permission prompts.
  //   3. Share-sheet handover to whatever the user picks (Files, AirDrop,
  //      Slack, Notes…).
  //
  // The status guards mean this only fires when the worker has actually
  // written a graph — the button is hidden otherwise (see JSX below).
  const handleDownloadGraph = useCallback(async () => {
    if (!document?.cypher_download_url) {
      Alert.alert('Graph not ready', 'This document does not yet have a generated knowledge graph. ' + 'Wait for status to reach Extracted, then try again.');
      return;
    }

    const isAvailable = await Sharing.isAvailableAsync();
    if (!isAvailable) {
      Alert.alert('Sharing unavailable', 'Sharing is not available on this device.');
      return;
    }

    const fileName = `${document.document_id}_graph.cypher`;
    const localPath = `${FileSystem.cacheDirectory}${fileName}`;

    try {
      // downloadAsync streams the signed URL directly into the cache dir
      // — never holding the full body in JS memory. Same expo-file-system
      // legacy entry point we use for uploads.
      const result = await FileSystem.downloadAsync(document.cypher_download_url, localPath);
      if (result.status < 200 || result.status >= 300) {
        throw new Error(`HTTP ${result.status}`);
      }

      await Sharing.shareAsync(result.uri, {
        // Cypher is a plain-text format. text/plain lets receiving apps
        // (Files, Notes, Slack) preview the contents instead of treating
        // it as an opaque binary blob.
        mimeType: 'text/plain',
        UTI: 'public.plain-text',
        dialogTitle: 'Download knowledge graph (Cypher)',
      });
    } catch (err) {
      console.error('Cypher download failed:', err);
      Alert.alert('Download failed', 'Could not download the knowledge graph. The signed URL may have expired — pull to refresh and try again.');
    }
  }, [document?.cypher_download_url, document?.document_id]);

  const handleStartExtraction = useCallback(() => {
    if (!document || document.status !== 'pending_upload') {
      return;
    }
  }, [document]);

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

        {document.status === 'failed' && <FailureCard processingStep={document.processing_step} error={document.error} />}

        {document.status === 'uploaded' && <CButton onPress={handleStartExtraction}>Start knowledge extraction</CButton>}

        {/* Only render the button when there's a real signed URL to hit.
            Avoids the user clicking a button that produces no result —
            a worse UX than not seeing the button at all. */}
        {document.cypher_download_url && <CButton onPress={handleDownloadGraph}>Download graph</CButton>}

        {ocrTextEnabled && <OcrTextCard extraction={extraction} isLoading={extractionIsLoading} isError={extractionIsError} />}

        <YStack gap={12}>
          <CText variant="h2" color="$color11">
            Pages
          </CText>

          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <XStack gap={12} pb={8}>
              {document.files.map((file, index) => (
                <DocumentPageThumbnail key={file.file_id} page={{ id: file.file_id, pageNumber: index + 1 }} />
              ))}
            </XStack>
          </ScrollView>
        </YStack>
      </YStack>
    </ScrollView>
  );
}
