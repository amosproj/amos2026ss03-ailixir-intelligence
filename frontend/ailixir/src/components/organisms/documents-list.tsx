import { DocumentListItem, type DocumentListItemData } from '@/components/molecules';
import { ScrollView, YStack } from 'tamagui';

export type DocumentsListProps = {
  documents: DocumentListItemData[];
};

export const DocumentsList = ({ documents }: DocumentsListProps) => {
  return (
    <ScrollView showsVerticalScrollIndicator>
      <YStack mt={10} gap={10}>
        {documents.map((document) => (
          <DocumentListItem key={document.id} document={document} />
        ))}
      </YStack>
    </ScrollView>
  );
};
