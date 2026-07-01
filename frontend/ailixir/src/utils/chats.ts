import type { RecentChat } from '@/data/home';
import type { ChatSummary } from '@/lib/chat-rtdb';

const MS_PER_DAY = 24 * 60 * 60 * 1000;

/**
 * Short, relative timestamp for a chat row — mirrors the convention common
 * chat apps use:
 *   today      -> "4:05 PM"
 *   yesterday  -> "Yesterday"
 *   this year  -> "May 21"
 *   older      -> "May 21, 2024"
 */
function formatTimeLabel(timestampMs: number): string {
  const when = new Date(timestampMs);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - MS_PER_DAY;

  if (timestampMs >= startOfToday) {
    return when.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  }
  if (timestampMs >= startOfYesterday) {
    return 'Yesterday';
  }
  const sameYear = when.getFullYear() === now.getFullYear();
  return when.toLocaleDateString(undefined, sameYear ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' });
}

export function chatSummaryToRecentChat(summary: ChatSummary): RecentChat {
  return {
    id: summary.chatId,
    title: summary.title,
    // A freshly-created chat has no messages yet; show a neutral placeholder
    // rather than an empty line.
    preview: summary.lastMessagePreview?.trim() || 'No messages yet',
    timeLabel: formatTimeLabel(summary.lastMessageAt),
  };
}
