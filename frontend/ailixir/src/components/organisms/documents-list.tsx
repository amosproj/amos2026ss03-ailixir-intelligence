import { DocumentListItem } from '@/components/molecules';
import { Document } from '@/interfaces/document';
import { ScrollView, YStack } from 'tamagui';

type DocumentsListProps = {
  documents: Document[];
};

const DocumentsList = ({ documents }: DocumentsListProps) => {
  return (
    <ScrollView showsVerticalScrollIndicator>
      <YStack mt={10} gap={10}>
        {documents.map((document) => (
          <DocumentListItem key={document.title} document={document} />
        ))}
      </YStack>
    </ScrollView>
  );
};

export default DocumentsList;
