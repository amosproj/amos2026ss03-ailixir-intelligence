import { getAuth } from 'firebase/auth';

import { CText } from '@/components/atoms';
import { QuickActionsGrid, RecentChatsSection } from '@/components/organisms';
import { quickActions, recentChats } from '@/data/home';
import { ScrollView, YStack } from 'tamagui';

export default function HomeScreen() {
  const auth = getAuth();
  const displayName = auth.currentUser?.displayName?.trim();

  return (
    <ScrollView flex={1} bg="$background">
      <YStack gap={14} px={16} py={16}>
        <YStack px={6} pb={4}>
          <CText variant="h2">Welcome back {displayName || ''}</CText>
          <CText variant="lead" mt={4}>
            What do you want to explore today?
          </CText>
        </YStack>

        <QuickActionsGrid actions={quickActions} />
        <RecentChatsSection chats={recentChats} />
      </YStack>
    </ScrollView>
  );
}
