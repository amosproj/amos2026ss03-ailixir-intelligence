import { CButton, CText } from '@/components/atoms';
import { DocumentPageThumbnail } from '@/components/molecules';
import { MOCK_DOCUMENTS } from '@/constants/mock-documents';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { ChevronLeft, FileText } from '@tamagui/lucide-icons-2';
import React from 'react';
import { ScrollView, XStack, YStack } from 'tamagui';

function DetailRow({ label, value }: { label: string; value?: string }) {
  if (!value) {
    return null;
  }

  return (
    <YStack gap={4} width="48%">
      <CText variant="caption" color="#6D6D6D">
        {label}
      </CText>
      <CText variant="body" bold color="#111111">
        {value}
      </CText>
    </YStack>
  );
}

export default function DocumentScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();

  const document = MOCK_DOCUMENTS.find((entry) => entry.id === params.id);

  if (!document) {
    return (
      <YStack flex={1} justify="center" items="center" px={24} bg="$background">
        <CText variant="h2" color="#111111">
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

  return (
    <ScrollView flex={1} bg="$background" showsVerticalScrollIndicator={false}>
      <YStack gap={20} px={16} pt={16} pb={32}>
        <XStack items="center" gap={12}>
          <CButton icon={ChevronLeft} onPress={() => router.back()} />
          <CText variant="h1" color="#111111" flex={1}>
            {document.title}
          </CText>
        </XStack>

        <YStack gap={16} bg="#FFFFFF" p={16} borderWidth={1} borderColor="#E4E4E4" style={{ borderRadius: 20 }}>
          <XStack items="center" gap={12}>
            <XStack width={48} height={48} bg="#EDEDED" items="center" justify="center" style={{ borderRadius: 14 }}>
              <FileText size={24} color="#111111" />
            </XStack>
            <YStack gap={4} flex={1}>
              <CText variant="caption" color="#6D6D6D">
                Status
              </CText>
              <CText variant="lead" bold color="#111111">
                {document.status ?? 'Unknown'}
              </CText>
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
            <CText variant="caption" color="#6D6D6D">
              Tags
            </CText>
            <XStack flexWrap="wrap" gap={8}>
              {document.tags.map((tag) => (
                <XStack key={tag} px={12} py={6} bg="#E8F7ED" style={{ borderRadius: 999 }}>
                  <CText variant="caption" color="#1F7A3A">
                    #{tag}
                  </CText>
                </XStack>
              ))}
            </XStack>
          </YStack>
        </YStack>

        <YStack gap={12}>
          <CText variant="h2" color="#111111">
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
