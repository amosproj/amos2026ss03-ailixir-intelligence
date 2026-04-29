import { CText } from '@/components/atoms';
import { Link } from 'expo-router';
import React from 'react';

export default function DocumentsScreen() {
  return (
    <>
      <CText>Documents Page</CText>
      <Link href="./capture/" asChild>
        <CText>Go to Capture</CText>
      </Link>
    </>
  );
}
