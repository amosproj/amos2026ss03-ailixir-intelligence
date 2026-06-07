import type { RecentChat } from '@/data/home';

import { CButton, CText } from '@/components/atoms';
import { RecentChatItem } from '@/components/molecules';
import { Link } from 'expo-router';
import { XStack, YStack } from 'tamagui';

type RecentChatsSectionProps = {
  chats: RecentChat[];
};

export function RecentChatsSection({ chats }: RecentChatsSectionProps) {
  return (
    <YStack gap={10}>
      <XStack justify="space-between" items="center" px={6} mt={10}>
        <CText variant="h2">Recent Chats</CText>
        <Link href="/chats" asChild>
          <CButton pr={0}>
            <CText variant="lead" bold color={'$accent10'}>
              View All
            </CText>
          </CButton>
        </Link>
      </XStack>

      <YStack gap={10}>
        {chats.map((chat) => (
          <RecentChatItem key={chat.id} chat={chat} />
        ))}
      </YStack>
    </YStack>
  );
}
