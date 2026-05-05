import { AuxiliaryOverview, ListFilters } from '@/components/molecules';
import { DocumentsAction } from '@/components/molecules/documents-action';
import DocumentsList from '@/components/organisms/documents-list';

import { Document } from '@/interfaces/document';
import React, { useState } from 'react';
import { YStack } from 'tamagui';

const MOCK_DOCUMENTS: Document[] = [
  {
    id: '1',
    title: 'Blood Test Results',
    timestamp: '12.03.2026',
    size: '425kb',
    type: 'pdf',
    tags: ['Lab Result', 'Blood Test'],
  },
  {
    id: '2',
    title: 'MRI Scan Report',
    timestamp: '05.02.2026',
    size: '1.2mb',
    type: 'pdf',
    tags: ['Medical Report', 'MRI'],
  },
  {
    id: '3',
    title: 'Prescription - Dr. Smith',
    timestamp: '20.01.2026',
    size: '150kb',
    type: 'pdf',
    tags: ['Prescription', 'Demotag'],
  },
  {
    id: '4',
    title: 'X-Ray Chest Analysis',
    timestamp: '15.12.2025',
    size: '980kb',
    type: 'pdf',
    tags: ['Medical Report', 'X-Ray'],
  },
  {
    id: '5',
    title: 'Test Summary',
    timestamp: '03.11.2025',
    size: '310kb',
    type: 'pdf',
    tags: ['Lab Result', 'Test'],
  },
  {
    id: '6',
    title: 'Vaccination Certificate',
    timestamp: '27.10.2025',
    size: '205kb',
    type: 'pdf',
    tags: ['Certificate', 'Vaccination'],
  },
];

export default function DocumentsScreen() {
  const [activeFilter, setActiveFilter] = useState('ALL');

  const overviewItems = ['6 Documents', '2 Uploads pending', 'Another information'];

  const onScanDocument = () => {
    // Placeholder for scan document functionality
    alert('Scan document functionality is not implemented yet.');
  };

  const onUploadDocument = () => {
    // Placeholder for upload document functionality
    alert('Upload document functionality is not implemented yet.');
  };

  const filterItems = ['ALL', 'MEDICAL REPORTS', 'LAB RESULTS'];

  return (
    <YStack flex={1} bg="#F2F2F2" pt={10} px={16}>
      <AuxiliaryOverview items={overviewItems} />
      <DocumentsAction onUploadDocument={onUploadDocument} onScanDocument={onScanDocument} />
      <ListFilters items={filterItems} active={activeFilter} setActive={setActiveFilter} />
      <DocumentsList documents={MOCK_DOCUMENTS} />
    </YStack>
  );
}
