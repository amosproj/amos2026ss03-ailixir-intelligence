import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useExternalStoreRuntime } from '@assistant-ui/core/react';
import type { AppendMessage, AssistantRuntime, MessageStatus, ThreadMessageLike } from '@assistant-ui/react-native';
import { getAuth } from 'firebase/auth';
import type { Unsubscribe } from 'firebase/database';
import apiClient from '@/lib/axios';
import type { ChatMessageRecord } from '@/lib/chat-rtdb';
import { addUserMessage, addAssistantPlaceholder, resolveAssistantMessage, subscribeMessages } from '@/lib/chat-rtdb';
import type { ChatMessage } from '@/components/organisms/chat-messages';

export interface UseChatRuntimeParams {
  chatId: string;
}

export interface UseChatRuntimeResult {
  runtime: AssistantRuntime;
  messages: ChatMessage[];
  isRunning: boolean;
}

const rtdbToThreadMessageLike = (msg: ChatMessageRecord): ThreadMessageLike => {
  let status: MessageStatus;
  switch (msg.status) {
    case 'pending':
      status = { type: 'running' };
      break;
    case 'sent':
      status = { type: 'complete', reason: 'stop' };
      break;
    case 'error':
      status = { type: 'incomplete', reason: 'error' };
      break;
    default:
      status = { type: 'complete', reason: 'stop' };
  }

  return {
    id: msg.messageId,
    role: msg.role,
    createdAt: new Date(msg.createdAt),
    content: [{ type: 'text', text: msg.content }],
    status,
  };
};

const rtdbToChatMessage = (msg: ChatMessageRecord): ChatMessage => ({
  id: msg.messageId,
  text: msg.content,
  timestamp: new Date(msg.createdAt),
  role: msg.role === 'system' ? 'assistant' : msg.role,
});

function getUid(): string {
  const user = getAuth().currentUser;
  if (!user?.uid) {
    throw new Error('User not authenticated');
  }
  return user.uid;
}

async function sendAndStream(uid: string, chatId: string, content: string, signal: AbortSignal, onChunk: (fullText: string) => void): Promise<string> {
  const response = await apiClient.post(`/chats/${chatId}/messages`, { content }, { signal });

  const reply = response.data?.content || response.data?.answer || JSON.stringify(response.data);
  onChunk(reply);
  return reply;
}

export function useChatRuntime({ chatId }: UseChatRuntimeParams): UseChatRuntimeResult {
  const uid = getUid();
  const [rtdbMessages, setRtdbMessages] = useState<ChatMessageRecord[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const pendingAssistantIdRef = useRef<string | null>(null);

  useEffect(() => {
    const unsub = subscribeMessages(
      uid,
      chatId,
      (messages) => {
        setRtdbMessages(messages);
      },
      (error) => {
        console.error('Failed to subscribe to messages:', error);
      },
    );

    return () => {
      unsub();
    };
  }, [uid, chatId]);

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const text = message.content
        .map((p) => (p.type === 'text' ? p.text : ''))
        .join('')
        .trim();
      if (!text) return;

      const abort = new AbortController();
      abortRef.current = abort;
      setIsRunning(true);

      try {
        await addUserMessage(uid, chatId, { content: text });

        const assistantId = await addAssistantPlaceholder(uid, chatId, { content: '' });
        pendingAssistantIdRef.current = assistantId;

        let accumulated = '';
        const reply = await sendAndStream(uid, chatId, text, abort.signal, (chunk) => {
          accumulated = chunk;
          void resolveAssistantMessage(uid, chatId, assistantId, {
            content: accumulated,
            status: 'sent',
          });
        });

        pendingAssistantIdRef.current = null;
        await resolveAssistantMessage(uid, chatId, assistantId, {
          content: reply,
          status: 'sent',
        });
      } catch (err) {
        if ((err as Error)?.name === 'AbortError' || abort.signal.aborted) {
          if (pendingAssistantIdRef.current) {
            await resolveAssistantMessage(uid, chatId, pendingAssistantIdRef.current, {
              content: 'Generation cancelled.',
              status: 'error',
            });
          }
        } else if (pendingAssistantIdRef.current) {
          await resolveAssistantMessage(uid, chatId, pendingAssistantIdRef.current, {
            content: 'Sorry, an error occurred while generating a response.',
            status: 'error',
          });
        }
        pendingAssistantIdRef.current = null;
      } finally {
        abortRef.current = null;
        setIsRunning(false);
      }
    },
    [uid, chatId],
  );

  const onCancel = useCallback(async () => {
    abortRef.current?.abort();
    setIsRunning(false);
  }, []);

  const store = useMemo(
    () => ({
      messages: rtdbMessages,
      isRunning,
      onNew,
      onCancel,
      convertMessage: rtdbToThreadMessageLike,
    }),
    [rtdbMessages, isRunning, onNew, onCancel],
  );

  const runtime = useExternalStoreRuntime(store);
  const messages = useMemo(() => rtdbMessages.map(rtdbToChatMessage), [rtdbMessages]);

  return { runtime, messages, isRunning };
}
