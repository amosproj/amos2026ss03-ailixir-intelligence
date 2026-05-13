import { CText } from '@/components/atoms';
import { Document } from '@/interfaces/document';
import { FileText } from '@tamagui/lucide-icons-2';
import { XStack, YStack } from 'tamagui';

export type DocumentPageThumbnailProps = {
  page: NonNullable<Document['pages']>[number];
};

export function DocumentPageThumbnail({ page }: DocumentPageThumbnailProps) {
  return (
    <YStack width={136} gap={8}>
      <XStack height={180} bg="#FAFAFA" borderWidth={1} borderColor="#D8D8D8" items="center" justify="center" style={{ borderRadius: 16 }}>
        <YStack items="center" gap={10}>
          <FileText size={36} color="#4F4F4F" />
          <CText variant="caption" color="#4F4F4F">
            Preview
          </CText>
        </YStack>
      </XStack>

      <CText variant="caption" bold>
        Page {page.pageNumber ?? page.id}
      </CText>
    </YStack>
  );
}
