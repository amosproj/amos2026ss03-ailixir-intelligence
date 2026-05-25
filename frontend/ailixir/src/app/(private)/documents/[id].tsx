import { CButton, CText } from '@/components/atoms';
import { DocumentPageThumbnail } from '@/components/molecules';
import { useDocument } from '@/hooks/useDocument';
import { formatDate, formatSize } from '@/utils/format';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Sharing from 'expo-sharing';
import { Asset } from 'expo-asset';
import { ChevronLeft, FileText } from '@tamagui/lucide-icons-2';
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
  const { data: document, isLoading, isError } = useDocument(params.id);

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
    <ScrollView flex={1} bg="$background" showsVerticalScrollIndicator={false}>
      <YStack gap={20} px={16} pt={16} pb={32}>
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
                  {statusLabels[document.status]}
                </CText>
              </XStack>
            </YStack>
          </XStack>

          <XStack flexWrap="wrap" justify="space-between" gap={16}>
            <DetailRow label="Filename" value={fileLabel} />
            <DetailRow label="Size" value={sizeLabel} />
            <DetailRow label="Uploaded" value={uploadedDate} />
          </XStack>
        </YStack>

        {document.status === 'uploaded' && <CButton onPress={handleStartExtraction}>Start knowledge extraction</CButton>}

        <CButton onPress={handleDownloadGraph}>Download graph</CButton>

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
