import { useEffect, useState } from 'react';
import { getAuth } from 'firebase/auth';

import { RecentChatItem } from '@/components/molecules';
import type { RecentChat } from '@/data/home';
import { subscribeChats } from '@/lib/chat-rtdb';
import { chatSummaryToRecentChat } from '@/utils/chats';
import { ScrollView, YStack } from 'tamagui';

export default function ChatsScreen() {
  const auth = getAuth();
  const uid = auth.currentUser?.uid;

  const [chats, setChats] = useState<RecentChat[]>([]);

  useEffect(() => {
    if (!uid) return;

    const unsub = subscribeChats(uid, (summaries) => {
      setChats(summaries.map(chatSummaryToRecentChat));
    });

    return unsub;
  }, [uid]);

  return (
    // The navigation header already shows "Chats"; no in-body heading so the
    // screen matches the design's single-title layout.
    <ScrollView flex={1} bg="$background">
      <YStack gap={10} px={16} py={16}>
        {chats.map((chat) => (
          <RecentChatItem key={chat.id} chat={chat} deletable />
        ))}
      </YStack>
    </ScrollView>
  );
}
