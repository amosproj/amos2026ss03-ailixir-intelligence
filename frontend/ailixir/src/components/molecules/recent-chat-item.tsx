import { useCallback, useRef } from 'react';
import { Alert, type Animated } from 'react-native';
import { Swipeable } from 'react-native-gesture-handler';
import { router } from 'expo-router';
import { getAuth } from 'firebase/auth';
import { Sparkles, Trash2 } from '@tamagui/lucide-icons-2';
import { Circle, YStack } from 'tamagui';

import { CText } from '@/components/atoms';
import { ListItemContent } from '@/components/molecules';
import type { RecentChat } from '@/data/home';
import { deleteChat } from '@/lib/chat-rtdb';

type RecentChatItemProps = {
  chat: RecentChat;
  deletable?: boolean;
};

// Avatar + delete-action colours, taken from the chat-list design mockup.
// White circle so the sparkle stays visible on the lavender row card (a light
// lavender circle would blend into the card background and disappear).
const AVATAR_BG = '#FFFFFF';
const AVATAR_ICON = '#6F65F5'; // brand purple
const DELETE_BG = '#FF3B30'; // iOS destructive red
const DELETE_ACTION_WIDTH = 84;

function ChatAvatar() {
  return (
    <Circle size={44} bg={AVATAR_BG}>
      <Sparkles size={22} color={AVATAR_ICON} />
    </Circle>
  );
}

export function RecentChatItem({ chat, deletable = false }: RecentChatItemProps) {
  const isSwipeOpenRef = useRef(false);

  // Confirm-then-delete. `close` collapses the open swipe panel whether the
  // user cancels or the delete fails, so the row never gets stuck half-open.
  const confirmDelete = useCallback(
    (close: () => void) => {
      Alert.alert('Delete chat', 'Are you sure you want to delete this chat?', [
        { text: 'Cancel', style: 'cancel', onPress: close },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            const uid = getAuth().currentUser?.uid;
            if (!uid) {
              Alert.alert('Error', 'You must be logged in to delete chats.');
              close();
              return;
            }
            try {
              await deleteChat(uid, chat.id);
              // No need to close() — the row unmounts when the chat disappears
              // from the subscription.
            } catch (error) {
              console.error('Delete chat error:', error);
              Alert.alert('Error', 'Failed to delete chat. Please try again.');
              close();
            }
          },
        },
      ]);
    },
    [chat.id],
  );

  const handleOpenChat = useCallback(() => {
    if (isSwipeOpenRef.current) return;
    router.push(`/(private)/chats/${chat.id}`);
  }, [chat.id]);

  const row = <ListItemContent onPress={handleOpenChat} icon={<ChatAvatar />} title={chat.title} subtitle={chat.preview} contentAccessory={<CText variant="caption">{chat.timeLabel}</CText>} />;

  // Home "Recent Chats" rows aren't deletable — render the plain row.
  if (!deletable) return row;

  // Swipe left to reveal Delete. Legacy `Swipeable` is used deliberately: it
  // animates with React Native's core Animated API and needs no
  // reanimated/worklets babel plugin — which this project has never configured.
  // That keeps the gesture from forcing a build-tooling change.
  const renderRightActions = (_progress: Animated.AnimatedInterpolation<number>, _drag: Animated.AnimatedInterpolation<number>, swipeable: Swipeable) => (
    <YStack width={DELETE_ACTION_WIDTH} bg={DELETE_BG} items="center" justify="center" pressStyle={{ opacity: 0.85 }} onPress={() => confirmDelete(() => swipeable.close())}>
      <Trash2 size={22} color="#fff" />
    </YStack>
  );

  return (
    <Swipeable
      renderRightActions={renderRightActions}
      overshootRight={false}
      rightThreshold={40}
      onSwipeableOpen={() => {
        isSwipeOpenRef.current = true;
      }}
      onSwipeableClose={() => {
        isSwipeOpenRef.current = false;
      }}>
      {row}
    </Swipeable>
  );
}
