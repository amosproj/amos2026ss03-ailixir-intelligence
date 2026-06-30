import apiClient from '@/lib/axios';

export interface ChatApiHistoryItem {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatApiRequest {
  query: string;
  history: ChatApiHistoryItem[];
  // RTDB chat id. When sent on the first message the backend schedules
  // background title generation for this chat.
  chat_id?: string;
}

export interface ChatApiResponse {
  answer: string;
  contextualized_query: string;
  query_changed: boolean;
  facts_used: number;
  entities_used: number;
  // True when the backend scheduled a title for this chat. The title itself
  // arrives via the RTDB chat-list subscription, not in this response.
  title_generation_scheduled?: boolean;
}

export async function callChatApi(payload: ChatApiRequest): Promise<ChatApiResponse> {
  const { data } = await apiClient.post<ChatApiResponse>('/chat/query', payload);
  return data;
}
