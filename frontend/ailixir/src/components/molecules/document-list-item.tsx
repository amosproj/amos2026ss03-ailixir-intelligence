import { CText } from '@/components/atoms';
import { Document } from '@/interfaces/document';
import { Link } from 'expo-router';
import { ChevronRight, File } from '@tamagui/lucide-icons-2';
import { XStack, YStack } from 'tamagui';

export function DocumentListItem({ document }: { document: Document }) {
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
            <CText variant="caption" tag>
              {document.tags.map((tag) => `#${tag}`).join(' ')}
            </CText>
          </YStack>
        </XStack>

        <ChevronRight size={34} color="#111111" />
      </XStack>
    </Link>
  );
}
