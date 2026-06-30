'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { AssistantRuntimeProvider, useExternalStoreRuntime, type AppendMessage, type ThreadMessageLike } from '@assistant-ui/react';
import { subscribeMessages, addUserMessage, addAssistantPlaceholder, resolveAssistantMessage, removeMessage } from '@/lib/chat-rtdb';
import { callChatApi, type ChatApiHistoryItem } from '@/lib/chat-api';
import type { ChatMessageRecord } from '@/lib/chat-rtdb';
import type { ChatMessage } from '@/components/organisms/';
import { getAuth } from 'firebase/auth';
import { AxiosError } from 'axios';

const APPEND_TEXT = (msg: AppendMessage) => {
  const part = msg.content[0];
  if (part?.type !== 'text') throw new Error('Only text messages are supported');
  return part.text;
};

function recordToChatMessage(r: ChatMessageRecord): ChatMessage {
  return {
    id: r.messageId,
    text: r.content,
    timestamp: new Date(r.createdAt),
    role: r.role === 'user' ? 'user' : 'assistant',
  };
}

const chatMessageToThreadLike = (msg: ChatMessage): ThreadMessageLike => ({
  id: msg.id,
  role: msg.role,
  content: [{ type: 'text' as const, text: msg.text }],
  createdAt: msg.timestamp,
  ...(msg.role === 'assistant' ? { status: { type: 'complete' as const, reason: 'stop' as const } } : {}),
  metadata: {},
});

function recordsToHistory(records: ChatMessageRecord[]): ChatApiHistoryItem[] {
  return records.flatMap((record) => {
    if (record.status !== 'sent') return [];
    if (record.role !== 'user' && record.role !== 'assistant') return [];

    return [
      {
        role: record.role,
        content: record.content,
      },
    ];
  });
}

interface FirebaseRuntimeContextValue {
  messages: ChatMessage[];
  isRunning: boolean;
  sendMessage: (text: string) => Promise<void>;
  retryMessage: (messageId: string) => Promise<void>;
}

const FirebaseRuntimeContext = createContext<FirebaseRuntimeContextValue | null>(null);

export function useFirebaseRuntime(): FirebaseRuntimeContextValue {
  const ctx = useContext(FirebaseRuntimeContext);
  if (!ctx) throw new Error('useFirebaseRuntime must be used within FirebaseRuntimeProvider');
  return ctx;
}

interface FirebaseRuntimeProviderProps {
  chatId: string;
  children: React.ReactNode;
}

export function FirebaseRuntimeProvider({ chatId, children }: FirebaseRuntimeProviderProps) {
  const user = getAuth().currentUser;
  const uid = user?.uid;

  const [records, setRecords] = useState<ChatMessageRecord[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => {
    if (!uid) return;
    setRecords([]);
    const unsub = subscribeMessages(uid, chatId, setRecords);
    return unsub;
  }, [uid, chatId]);

  const messages = useMemo(() => records.map(recordToChatMessage), [records]);

  const onNew = useCallback(
    async (msg: AppendMessage) => {
      if (!uid) return;

      const text = APPEND_TEXT(msg);
      if (!text.trim()) return;

      let assistantId: string | null = null;
      setIsRunning(true);
      try {
        await addUserMessage(uid, chatId, { content: text });
        assistantId = await addAssistantPlaceholder(uid, chatId);

        const response = await callChatApi({
          query: text,
          history: recordsToHistory(records),
          // Sent so the backend can auto-title this chat from the first
          // message. It only acts when history is empty (first turn); the
          // generated title arrives via the chat-list subscription.
          chat_id: chatId,
        });

        await resolveAssistantMessage(uid, chatId, assistantId, {
          content: response.answer,
          status: 'sent',
        });
      } catch (err) {
        console.error('Failed to send message:', err);

        const fallbackAssistantId = assistantId ?? (await addAssistantPlaceholder(uid, chatId));
        const isGatewayTimeout = err instanceof AxiosError && err.response?.status === 504;
        await resolveAssistantMessage(uid, chatId, fallbackAssistantId, {
          content: isGatewayTimeout ? 'The assistant took too long to respond. Please try again.' : 'I could not reach the assistant service. Please try again.',
          status: 'error',
        });
      } finally {
        setIsRunning(false);
      }
    },
    [uid, chatId, records],
  );

  const runtime = useExternalStoreRuntime({
    messages,
    isRunning,
    onNew,
    convertMessage: chatMessageToThreadLike,
  });

  const sendMessage = useCallback(
    async (text: string) => {
      runtime.thread.append({
        content: [{ type: 'text', text }],
        role: 'user',
      });
    },
    [runtime],
  );

  const retryMessage = useCallback(
    async (messageId: string) => {
      if (!uid) return;

      const selectedAssistantIndex = records.findIndex((record) => record.messageId === messageId);
      if (selectedAssistantIndex < 0) return;

      const selectedAssistant = records[selectedAssistantIndex];
      if (selectedAssistant.role !== 'assistant') return;

      const retryContextRecords = records.slice(0, selectedAssistantIndex);
      const previousUserMessage = [...retryContextRecords].reverse().find((record) => record.role === 'user' && record.status === 'sent');
      if (!previousUserMessage) return;

      let assistantId: string | null = null;
      setIsRunning(true);
      try {
        await removeMessage(uid, chatId, selectedAssistant.messageId);
        assistantId = await addAssistantPlaceholder(uid, chatId);

        const response = await callChatApi({
          query: previousUserMessage.content,
          history: recordsToHistory(retryContextRecords),
        });

        await resolveAssistantMessage(uid, chatId, assistantId, {
          content: response.answer,
          status: 'sent',
        });
      } catch (err) {
        console.error('Failed to retry message:', err);

        const fallbackAssistantId = assistantId ?? (await addAssistantPlaceholder(uid, chatId));
        const isGatewayTimeout = err instanceof AxiosError && err.response?.status === 504;
        await resolveAssistantMessage(uid, chatId, fallbackAssistantId, {
          content: isGatewayTimeout ? 'The assistant took too long to respond. Please try again.' : 'I could not reach the assistant service. Please try again.',
          status: 'error',
        });
      } finally {
        setIsRunning(false);
      }
    },
    [uid, chatId, records],
  );

  const ctxValue = useMemo(() => ({ messages, isRunning, sendMessage, retryMessage }), [messages, isRunning, sendMessage, retryMessage]);

  return (
    <FirebaseRuntimeContext.Provider value={ctxValue}>
      <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
    </FirebaseRuntimeContext.Provider>
  );
}
