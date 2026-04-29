import { Link } from 'expo-router';
import { Platform } from 'react-native';

import { ThemedView } from '@/components/themed-view';
import { WebBadge } from '@/components/web-badge';
import { CText } from '@/components/atoms';

export default function HomeScreen() {
  return (
    <ThemedView>
      <>
        <CText fontSize={40}>Welcome to Ailixir!</CText>

        <Link href="/documents/" asChild>
          <CText>Go to Documents</CText>
        </Link>
        <Link href="/chats/" asChild>
          <CText>Chats</CText>
        </Link>

        {Platform.OS === 'web' && <WebBadge />}
      </>
    </ThemedView>
  );
}
