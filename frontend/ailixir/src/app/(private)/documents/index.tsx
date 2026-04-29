import { CText } from '@/components/atoms';
import { Link } from 'expo-router';
import React from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function DocumentsScreen() {
  return (
    <SafeAreaView>
      <CText>Documents Page</CText>
      <Link href="./capture/" asChild>
        <CText>Go to Capture</CText>
      </Link>
    </SafeAreaView>
  );
}
