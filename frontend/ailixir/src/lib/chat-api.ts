import apiClient from '@/lib/axios';

export interface ChatApiHistoryItem {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatApiRequest {
  query: string;
  history: ChatApiHistoryItem[];
}

export interface ChatApiResponse {
  answer: string;
  contextualized_query: string;
  query_changed: boolean;
  facts_used: number;
  entities_used: number;
}

export async function callChatApi(payload: ChatApiRequest): Promise<ChatApiResponse> {
  const { data } = await apiClient.post<ChatApiResponse>('/chat/query', payload);
  return data;
}
