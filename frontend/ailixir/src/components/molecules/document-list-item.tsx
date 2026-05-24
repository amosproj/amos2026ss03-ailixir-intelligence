import { CText } from '@/components/atoms';
import type { DocumentStatus } from '@/hooks/useDocuments';
import { Link } from 'expo-router';
import { ChevronRight, File } from '@tamagui/lucide-icons-2';
import { XStack, YStack } from 'tamagui';

export type DocumentListItemData = {
  id: string;
  title: string;
  timestamp: string;
  size: string;
  status: DocumentStatus;
  tags?: string[];
};

const statusLabels: Record<DocumentStatus, string> = {
  pending_upload: 'Pending upload',
  uploaded: 'Uploaded',
  processing: 'Processing',
  extracted: 'Extracted',
  failed: 'Failed',
};

const statusStyles: Record<
  DocumentStatus,
  {
    backgroundColor: '$yellow2' | '$blue2' | '$orange2' | '$green2' | '$red2';
    color: '$yellow11' | '$blue11' | '$orange11' | '$green11' | '$red11';
  }
> = {
  pending_upload: { backgroundColor: '$yellow2', color: '$yellow11' },
  uploaded: { backgroundColor: '$blue2', color: '$blue11' },
  processing: { backgroundColor: '$orange2', color: '$orange11' },
  extracted: { backgroundColor: '$green2', color: '$green11' },
  failed: { backgroundColor: '$red2', color: '$red11' },
};

export function DocumentListItem({ document }: { document: DocumentListItemData }) {
  const statusStyle = statusStyles[document.status];

  return (
    <Link href={`/documents/${document.id}`} asChild>
      <XStack items="center" justify="space-between" px={20} py={16} bg="#ECECEC">
        <XStack items="center" gap={14} flex={1}>
          <File size={34} color="#111111" />
          <YStack gap={2}>
            <CText variant="lead" color="#111111">
              {document.title}
            </CText>
            <CText variant="caption">
              {document.timestamp} {document.size}
            </CText>
            <XStack items="center" gap={8} flexWrap="wrap">
              <XStack px={10} py={4} bg={statusStyle.backgroundColor} style={{ borderRadius: 999 }}>
                <CText variant="caption" color={statusStyle.color}>
                  {statusLabels[document.status]}
                </CText>
              </XStack>
              {!!document.tags?.length && (
                <CText variant="caption" tag>
                  {document.tags.map((tag) => `#${tag}`).join(' ')}
                </CText>
              )}
            </XStack>
          </YStack>
        </XStack>

        <ChevronRight size={34} color="#111111" />
      </XStack>
    </Link>
  );
}
