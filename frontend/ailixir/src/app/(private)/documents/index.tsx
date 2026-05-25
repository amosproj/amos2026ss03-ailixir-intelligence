import { AuxiliaryOverview } from '@/components/molecules';
import { DocumentsAction } from '@/components/molecules/documents-action';

import { DocumentsList } from '@/components/organisms/documents-list';
import { useDocuments } from '@/hooks/useDocuments';
import { formatDate, formatSize } from '@/utils/format';
import { router } from 'expo-router';
import React from 'react';
import { YStack } from 'tamagui';

export default function DocumentsScreen() {
  const { data } = useDocuments();
  const overviewItems = ['6 Documents', '2 Uploads pending', 'Another information'];

  const documents = (data?.documents ?? []).map((doc) => ({
    id: doc.document_id,
    title: doc.title,
    timestamp: formatDate(doc.created_at),
    size: formatSize(doc.total_bytes),
    status: doc.status,
    tags: [],
  }));

  const onScanDocument = () => {
    // Placeholder for scan document functionality
    alert('Scan document functionality is not implemented yet.');
  };

  const onUploadDocument = () => {
    router.navigate('/documents/upload');
  };

  return (
    <YStack flex={1} background="$background" pt={10} px={16}>
      <AuxiliaryOverview items={overviewItems} />
      <DocumentsAction onUploadDocument={onUploadDocument} onScanDocument={onScanDocument} />
      <DocumentsList documents={documents} />
    </YStack>
  );
}
