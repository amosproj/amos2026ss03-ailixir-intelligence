import type { RecentChat } from '@/data/home';
import type { ChatSummary } from '@/lib/chat-rtdb';

export function chatSummaryToRecentChat(summary: ChatSummary): RecentChat {
  const date = new Date(summary.lastMessageAt);
  const timeAgo = date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return { id: summary.chatId, title: summary.title, timeAgo };
}
