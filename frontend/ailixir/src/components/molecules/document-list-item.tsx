import { CText } from '@/components/atoms';
import { DeleteButton, ListItemContent } from '@/components/molecules';
import type { DocumentStatus } from '@/hooks/useDocuments';
import { ArrowRight, File, Trash2 } from '@tamagui/lucide-icons-2';
import { XStack } from 'tamagui';

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
    <ListItemContent
      href={`/documents/${document.id}`}
      icon={<File size={22} />}
      title={document.title}
      subtitle={`${document.timestamp} ${document.size}`}
      meta={
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
      }
      contentAccessory={
        document.status !== 'processing' ? (
          <DeleteButton documentId={document.id} circular>
            <Trash2 size={20} color="red" />
          </DeleteButton>
        ) : null
      }
      endAdornment={<ArrowRight size={22} />}
    />
  );
}
