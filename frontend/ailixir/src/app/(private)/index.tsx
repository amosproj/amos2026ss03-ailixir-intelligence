import { useCallback, useEffect, useState } from 'react';
import { getAuth } from 'firebase/auth';
import { router } from 'expo-router';

import { CText } from '@/components/atoms';
import { QuickActionsGrid, RecentChatsSection } from '@/components/organisms';
import { quickActions } from '@/data/home';
import type { RecentChat } from '@/data/home';
import { subscribeChats, createChat } from '@/lib/chat-rtdb';
import { chatSummaryToRecentChat } from '@/utils/chats';
import { ScrollView, YStack } from 'tamagui';

const RECENT_CHATS_LIMIT = 4;

export default function HomeScreen() {
  const auth = getAuth();
  const uid = auth.currentUser?.uid;
  const displayName = auth.currentUser?.displayName?.trim();

  const [chats, setChats] = useState<RecentChat[]>([]);

  useEffect(() => {
    if (!uid) return;
    const unsub = subscribeChats(uid, (summaries) => {
      setChats(summaries.map(chatSummaryToRecentChat));
    });
    return unsub;
  }, [uid]);

  const handleNewChat = useCallback(async () => {
    if (!uid) return;
    const chatId = await createChat(uid);
    router.push(`/(private)/chats/${chatId}`);
  }, [uid]);

  const actions = quickActions.map((a) => (a.title === 'New Chat' ? { ...a, onPress: handleNewChat } : a));

  return (
    <ScrollView flex={1} bg="$background">
      <YStack gap={14} px={16} py={16}>
        <YStack px={6} pb={4}>
          <CText variant="h2">Welcome back {displayName || ''}</CText>
          <CText variant="lead" mt={4}>
            What do you want to explore today?
          </CText>
        </YStack>

        <QuickActionsGrid actions={actions} />
        <RecentChatsSection chats={chats.slice(0, RECENT_CHATS_LIMIT)} />
      </YStack>
    </ScrollView>
  );
}
