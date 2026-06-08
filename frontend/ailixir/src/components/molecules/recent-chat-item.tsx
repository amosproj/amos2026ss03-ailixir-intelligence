import type { RecentChat } from '@/data/home';

import { ListItemContent } from '@/components/molecules';
import { MessageCircle } from '@tamagui/lucide-icons-2';

type RecentChatItemProps = {
  chat: RecentChat;
};

export function RecentChatItem({ chat }: RecentChatItemProps) {
  return <ListItemContent href="/chats" icon={<MessageCircle size={22} />} title={chat.title} subtitle={chat.timeAgo} />;
}
