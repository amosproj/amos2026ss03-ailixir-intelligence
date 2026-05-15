import { Link } from 'expo-router';

import { CText } from '@/components/atoms';
import { YStack } from 'tamagui';

export default function HomeScreen() {
  return (
    <YStack width="100%" height="100%" background="$background" justify="center" items="center" gap={10}>
      <CText variant="h1">Welcome to Ailixir!</CText>

      <Link href="/documents" asChild>
        <CText>Go to Documents</CText>
      </Link>
      <Link href="/chats" asChild>
        <CText>Chats</CText>
      </Link>
    </YStack>
  );
}
