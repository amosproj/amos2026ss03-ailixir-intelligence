import { AuxiliaryOverview, ListFilters } from '@/components/molecules';
import { DocumentsAction } from '@/components/molecules/documents-action';

import { DocumentsList } from '@/components/organisms/documents-list';
import { documentsAtom } from '@/lib/documentAtoms';
import { router } from 'expo-router';
import React, { useState } from 'react';
import { useAtomValue } from 'jotai';
import { YStack } from 'tamagui';

export default function DocumentsScreen() {
  const [activeFilter, setActiveFilter] = useState('ALL');
  const documents = useAtomValue(documentsAtom);

  const overviewItems = ['6 Documents', '2 Uploads pending', 'Another information'];

  const onScanDocument = () => {
    // Placeholder for scan document functionality
    alert('Scan document functionality is not implemented yet.');
  };

  const onUploadDocument = () => {
    router.navigate('/documents/upload');
  };

  const filterItems = ['ALL', 'MEDICAL REPORTS', 'LAB RESULTS'];

  return (
    <YStack flex={1} background="$background" pt={10} px={16}>
      <AuxiliaryOverview items={overviewItems} />
      <DocumentsAction onUploadDocument={onUploadDocument} onScanDocument={onScanDocument} />
      <ListFilters items={filterItems} active={activeFilter} setActive={setActiveFilter} />
      <DocumentsList documents={documents} />
    </YStack>
  );
}
