'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { AssistantRuntimeProvider, useExternalStoreRuntime, type AppendMessage, type ThreadMessageLike } from '@assistant-ui/react';
import { subscribeMessages, addUserMessage, addAssistantPlaceholder, resolveAssistantMessage } from '@/lib/chat-rtdb';
import type { ChatMessageRecord } from '@/lib/chat-rtdb';
import type { ChatMessage } from '@/components/organisms/chat-messages';
import { getAuth } from 'firebase/auth';

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
  status: { type: 'complete' as const, reason: 'stop' as const },
  metadata: {},
});

interface FirebaseRuntimeContextValue {
  messages: ChatMessage[];
  isRunning: boolean;
  sendMessage: (text: string) => Promise<void>;
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

      setIsRunning(true);
      try {
        await addUserMessage(uid, chatId, { content: text });
        const assistantId = await addAssistantPlaceholder(uid, chatId);

        const response = await simulateBackendCall(text);

        await resolveAssistantMessage(uid, chatId, assistantId, {
          content: response,
          status: 'sent',
        });
      } catch (err) {
        console.error('Failed to send message:', err);
      } finally {
        setIsRunning(false);
      }
    },
    [uid, chatId],
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

  const ctxValue = useMemo(() => ({ messages, isRunning, sendMessage }), [messages, isRunning, sendMessage]);

  return (
    <FirebaseRuntimeContext.Provider value={ctxValue}>
      <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
    </FirebaseRuntimeContext.Provider>
  );
}

async function simulateBackendCall(_input: string): Promise<string> {
  await new Promise((r) => setTimeout(r, 1500));
  return 'Simulated assistant response – backend integration pending.';
}
