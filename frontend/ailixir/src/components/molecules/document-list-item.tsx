import { CText } from '@/components/atoms';
import { Document, DocumentDraft } from '@/interfaces/document';
import { Link } from 'expo-router';
import { ChevronRight, File } from '@tamagui/lucide-icons-2';
import { XStack, YStack } from 'tamagui';

type DocumentListItemProps = {
  document: Document | DocumentDraft;
};

export function DocumentListItem({ document }: DocumentListItemProps) {
  const isDraft = !('id' in document);
  const title = document.title || 'Draft Document';
  const size = document.size || 'Size pending';
  const timestamp = 'timestamp' in document ? document.timestamp : 'Draft';
  const tags = 'tags' in document ? document.tags : [];

  const content = (
    <XStack items="center" justify="space-between" px={20} py={16} bg="#ECECEC">
      <XStack items="center" gap={14} flex={1}>
        <File size={34} color="#111111" />
        <YStack gap={2}>
          <CText variant="lead" color="#111111">
            {title}
          </CText>
          <CText variant="caption">
            {timestamp} {size}
          </CText>
          {!!tags.length && (
            <CText variant="caption" tag>
              {tags.map((tag) => `#${tag}`).join(' ')}
            </CText>
          )}
        </YStack>
      </XStack>

      <ChevronRight size={34} color="#111111" />
    </XStack>
  );

  if (isDraft) {
    return content;
  }

  return (
    <Link href={`/documents/${document.id}`} asChild>
      {content}
    </Link>
  );
}
