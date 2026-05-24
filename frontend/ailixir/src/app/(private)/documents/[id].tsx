import { CButton, CText } from '@/components/atoms';
import { DocumentPageThumbnail } from '@/components/molecules';
import { documentsAtom, updateDocumentStatusAtom } from '@/lib/documentAtoms';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Sharing from 'expo-sharing';
import { Asset } from 'expo-asset';
import { ChevronLeft, FileText } from '@tamagui/lucide-icons-2';
import React, { useCallback } from 'react';
import { Alert } from 'react-native';
import { ScrollView, XStack, YStack } from 'tamagui';
import { useAtomValue, useSetAtom } from 'jotai';
import apiClient from '@/lib/axios';
import { useQuery } from '@tanstack/react-query';

const statusLabels = {
  not_extracted: 'Not extracted',
  extracting: 'Extraction in progress',
  extracted: 'Knowledge extracted',
} as const;

const statusStyles = {
  not_extracted: { backgroundColor: '$yellow2', color: '$yellow11' },
  extracting: { backgroundColor: '$blue2', color: '$blue11' },
  extracted: { backgroundColor: '$green2', color: '$green11' },
} as const;

function DetailRow({ label, value }: { label: string; value?: string }) {
  if (!value) {
    return null;
  }

  return (
    <YStack gap={4} width="48%">
      <CText variant="caption" color="$color9">
        {label}
      </CText>
      <CText variant="body" bold color="$color11">
        {value}
      </CText>
    </YStack>
  );
}

export default function DocumentScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const documents = useAtomValue(documentsAtom);
  const updateDocumentStatus = useSetAtom(updateDocumentStatusAtom);

  const document = documents.find((entry) => entry.id === params.id);

  const { data, error } = useQuery({
    queryKey: ['documentExtraction', document?.id],
    queryFn: () => {
      if (!document) {
        return new Promise(() => ({ status: 'failed' }));
      }

      return apiClient.get(`/documents/${document.id}`);
    },
    refetchInterval: (query) => {
      // Stop polling once the job finishes
      const extractionSuccessful = (query.state.data as any)?.status === 'extracted';
      const extractionFailed = (query.state.data as any)?.status === 'failed';

      if (extractionSuccessful || extractionFailed) return false;
      return 3_000;
    },
  });

  const handleDownloadGraph = useCallback(async () => {
    const isAvailable = await Sharing.isAvailableAsync();

    if (!isAvailable) {
      Alert.alert('Sharing unavailable', 'Sharing is not available on this device.');
      return;
    }

    const graphAsset = Asset.fromModule(require('../../../static/graph-1.png'));
    await graphAsset.downloadAsync();

    const uri = graphAsset.localUri ?? graphAsset.uri;
    await Sharing.shareAsync(uri, {
      mimeType: 'image/png',
      UTI: 'public.png',
      dialogTitle: 'Download graph',
    });
  }, []);

  const handleStartExtraction = useCallback(async () => {
    if (!document || document.status !== 'not_extracted') {
      return;
    }

    updateDocumentStatus({ documentId: document.id, status: 'extracting' });

    // // TODO: replace with proper endpoint when one is implemented
    // await apiClient.post(`/documents/${document.id}/extract`);

    // const resp = await apiClient.get(`/documents/${document.id}`);
    // let lastStatus = resp.data.status;

    // while (lastStatus === 'processing') {
    //   await new Promise((resolve) => setTimeout(resolve, 1000));
    //   const updatedResp = await apiClient.get(`/documents/${document.id}`);
    //   lastStatus = updatedResp.data.status;
    // }

    // if (lastStatus === 'failed') {
    //   Alert.alert('Extraction failed', 'An error occurred during knowledge extraction.');
    //   updateDocumentStatus({ documentId: document.id, status: 'not_extracted' });
    //   return;
    // }

    // if (lastStatus === 'extracted') {
    //   updateDocumentStatus({ documentId: document.id, status: 'extracted' });
    // }
  }, [document, updateDocumentStatus]);

  if (!document) {
    return (
      <YStack flex={1} justify="center" items="center" px={24} bg="$background">
        <CText variant="h2" color="$color11">
          Document not found
        </CText>
        <CText variant="caption" style={{ textAlign: 'center' }}>
          The requested document is not available in the current mock data.
        </CText>
        <CButton icon={ChevronLeft} onPress={() => router.back()} mt={16}>
          Back
        </CButton>
      </YStack>
    );
  }

  const extractionStatus = data ? 'Loading...' : (data as any).status.replace('failed', 'xtraction failed');

  return (
    <ScrollView flex={1} bg="$background" showsVerticalScrollIndicator={false}>
      <YStack gap={20} px={16} pt={16} pb={32}>
        <XStack items="center" gap={12}>
          <CButton icon={ChevronLeft} onPress={() => router.back()} />
          <CText variant="h1" color="$color11" flex={1}>
            {document.title}
          </CText>
        </XStack>

        <YStack gap={16} bg="$color0" p={16} borderWidth={1} borderColor="$color3" style={{ borderRadius: 20 }}>
          <XStack items="center" gap={12}>
            <XStack width={48} height={48} bg="$color2" items="center" justify="center" style={{ borderRadius: 14 }}>
              <FileText size={24} color="$color11" />
            </XStack>
            <YStack gap={4} flex={1}>
              <CText variant="caption" color="$color9">
                Status
              </CText>
              <XStack px={10} py={4} bg={statusStyles[document.status].backgroundColor} style={{ borderRadius: 999, alignSelf: 'flex-start', flexShrink: 0, alignItems: 'center' }}>
                <CText variant="caption" color={statusStyles[document.status].color}>
                  {error ? 'Could not load status' : extractionStatus}
                </CText>
              </XStack>
            </YStack>
          </XStack>

          <XStack flexWrap="wrap" justify="space-between" gap={16}>
            <DetailRow label="Filename" value={document.fileName} />
            <DetailRow label="Size" value={document.size} />
            <DetailRow label="From" value={document.fromDate} />
            <DetailRow label="Uploaded" value={document.uploadedDate} />
            <DetailRow label="Facility" value={document.facilityName} />
          </XStack>

          <YStack gap={8}>
            <CText variant="caption" color="$color9">
              Tags
            </CText>
            <XStack flexWrap="wrap" gap={8}>
              {document.tags.map((tag) => (
                <XStack key={tag} px={12} py={6} bg="$color2" style={{ borderRadius: 999 }}>
                  <CText variant="caption" color="$color10">
                    #{tag}
                  </CText>
                </XStack>
              ))}
            </XStack>
          </YStack>
        </YStack>

        {/* {document.status === 'not_extracted' && <CButton onPress={handleStartExtraction}>Start knowledge extraction</CButton>} */}

        <CButton onPress={handleDownloadGraph}>Download graph</CButton>

        <YStack gap={12}>
          <CText variant="h2" color="$color11">
            Pages
          </CText>

          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <XStack gap={12} pb={8}>
              {(document.pages ?? []).map((page) => (
                <DocumentPageThumbnail key={page.id} page={page} />
              ))}
            </XStack>
          </ScrollView>
        </YStack>
      </YStack>
    </ScrollView>
  );
}
