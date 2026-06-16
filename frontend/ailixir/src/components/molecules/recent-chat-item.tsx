import type { RecentChat } from '@/data/home';

import { DeleteChatButton, ListItemContent } from '@/components/molecules';
import { MessageCircle, Trash2 } from '@tamagui/lucide-icons-2';

type RecentChatItemProps = {
  chat: RecentChat;
  deletable?: boolean;
};

export function RecentChatItem({ chat, deletable = false }: RecentChatItemProps) {
  return (
    <ListItemContent
      href={`/(private)/chats/${chat.id}`}
      icon={<MessageCircle size={22} />}
      title={chat.title}
      subtitle={chat.timeAgo}
      contentAccessory={
        deletable ? (
          <DeleteChatButton chatId={chat.id} circular>
            <Trash2 size={20} color="red" />
          </DeleteChatButton>
        ) : null
      }
    />
  );
}
