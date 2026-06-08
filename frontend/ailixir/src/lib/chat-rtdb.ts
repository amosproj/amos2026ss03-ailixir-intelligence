import '@/lib/firebase';
import { child, getDatabase, onValue, push, ref, remove, set, update, type Unsubscribe } from 'firebase/database';

export type ChatMessageRole = 'user' | 'assistant' | 'system';

export type ChatMessageStatus = 'pending' | 'sent' | 'error';

export interface ChatSummary {
  chatId: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  lastMessagePreview: string;
  lastMessageAt: number;
}

export interface ChatMessageRecord {
  messageId: string;
  role: ChatMessageRole;
  content: string;
  createdAt: number;
  status: ChatMessageStatus;
  requestId: string | null;
}

export interface CreateChatInput {
  title?: string;
}

export interface AddMessageInput {
  content: string;
  requestId?: string | null;
}

const DEFAULT_CHAT_TITLE = 'New Chat';
const MAX_PREVIEW_LENGTH = 140;

const db = getDatabase();

const chatsPath = (uid: string) => `users/${uid}/chats`;
const chatPath = (uid: string, chatId: string) => `users/${uid}/chats/${chatId}`;
const messagesPath = (uid: string, chatId: string) => `users/${uid}/chatMessages/${chatId}`;
const messagePath = (uid: string, chatId: string, messageId: string) => `users/${uid}/chatMessages/${chatId}/${messageId}`;

const toMessagePreview = (value: string) => value.trim().slice(0, MAX_PREVIEW_LENGTH);

const sortByUpdatedAtDesc = <T extends { updatedAt: number; createdAt: number }>(items: T[]) =>
  [...items].sort((a, b) => {
    if (b.updatedAt !== a.updatedAt) {
      return b.updatedAt - a.updatedAt;
    }
    return b.createdAt - a.createdAt;
  });

const sortByCreatedAtAsc = <T extends { createdAt: number }>(items: T[]) => [...items].sort((a, b) => a.createdAt - b.createdAt);

export async function createChat(uid: string, input: CreateChatInput = {}) {
  const chatRef = push(child(ref(db), chatsPath(uid)));
  const chatId = chatRef.key;

  if (!chatId) {
    throw new Error('Failed to generate chat id.');
  }

  const now = Date.now();
  const title = input.title?.trim() || DEFAULT_CHAT_TITLE;

  await set(chatRef, {
    title,
    createdAt: now,
    updatedAt: now,
    lastMessagePreview: '',
    lastMessageAt: now,
  });

  return chatId;
}

export async function renameChat(uid: string, chatId: string, title: string) {
  const nextTitle = title.trim();
  if (!nextTitle) {
    throw new Error('Chat title cannot be empty.');
  }

  await update(ref(db, chatPath(uid, chatId)), {
    title: nextTitle,
    updatedAt: Date.now(),
  });
}

export async function deleteChat(uid: string, chatId: string) {
  await update(ref(db), {
    [chatPath(uid, chatId)]: null,
    [messagesPath(uid, chatId)]: null,
  });
}

export async function addUserMessage(uid: string, chatId: string, input: AddMessageInput) {
  return addMessage(uid, chatId, {
    role: 'user',
    content: input.content,
    status: 'sent',
    requestId: input.requestId ?? null,
  });
}

export async function addAssistantPlaceholder(uid: string, chatId: string, input: AddMessageInput = { content: '' }) {
  return addMessage(uid, chatId, {
    role: 'assistant',
    content: input.content,
    status: 'pending',
    requestId: input.requestId ?? null,
  });
}

export async function resolveAssistantMessage(uid: string, chatId: string, messageId: string, input: AddMessageInput & { status?: Exclude<ChatMessageStatus, 'pending'> }) {
  const content = input.content;
  const now = Date.now();
  const preview = toMessagePreview(content);
  const status = input.status ?? 'sent';

  await update(ref(db), {
    [`${messagePath(uid, chatId, messageId)}/content`]: content,
    [`${messagePath(uid, chatId, messageId)}/status`]: status,
    [`${messagePath(uid, chatId, messageId)}/requestId`]: input.requestId ?? null,
    [`${chatPath(uid, chatId)}/updatedAt`]: now,
    [`${chatPath(uid, chatId)}/lastMessageAt`]: now,
    [`${chatPath(uid, chatId)}/lastMessagePreview`]: preview,
  });
}

export function subscribeChats(uid: string, onNext: (chats: ChatSummary[]) => void, onError?: (error: Error) => void): Unsubscribe {
  const chatsRef = ref(db, chatsPath(uid));
  return onValue(
    chatsRef,
    (snapshot) => {
      const value = snapshot.val() as Record<string, Omit<ChatSummary, 'chatId'>> | null;

      if (!value) {
        onNext([]);
        return;
      }

      const chats: ChatSummary[] = Object.entries(value).map(([chatId, chat]) => ({
        chatId,
        title: chat.title,
        createdAt: chat.createdAt,
        updatedAt: chat.updatedAt,
        lastMessagePreview: chat.lastMessagePreview,
        lastMessageAt: chat.lastMessageAt,
      }));

      onNext(sortByUpdatedAtDesc(chats));
    },
    (error) => {
      onError?.(error as Error);
    },
  );
}

export function subscribeMessages(uid: string, chatId: string, onNext: (messages: ChatMessageRecord[]) => void, onError?: (error: Error) => void): Unsubscribe {
  const messagesRef = ref(db, messagesPath(uid, chatId));
  return onValue(
    messagesRef,
    (snapshot) => {
      const value = snapshot.val() as Record<string, Omit<ChatMessageRecord, 'messageId'>> | null;

      if (!value) {
        onNext([]);
        return;
      }

      const messages: ChatMessageRecord[] = Object.entries(value).map(([messageId, message]) => ({
        messageId,
        role: message.role,
        content: message.content,
        createdAt: message.createdAt,
        status: message.status,
        requestId: message.requestId,
      }));

      onNext(sortByCreatedAtAsc(messages));
    },
    (error) => {
      onError?.(error as Error);
    },
  );
}

async function addMessage(uid: string, chatId: string, input: { role: ChatMessageRole; content: string; status: ChatMessageStatus; requestId: string | null }) {
  const messageRef = push(child(ref(db), messagesPath(uid, chatId)));
  const messageId = messageRef.key;

  if (!messageId) {
    throw new Error('Failed to generate message id.');
  }

  const now = Date.now();
  const preview = toMessagePreview(input.content);

  await update(ref(db), {
    [messagePath(uid, chatId, messageId)]: {
      role: input.role,
      content: input.content,
      createdAt: now,
      status: input.status,
      requestId: input.requestId,
    },
    [`${chatPath(uid, chatId)}/updatedAt`]: now,
    [`${chatPath(uid, chatId)}/lastMessageAt`]: now,
    [`${chatPath(uid, chatId)}/lastMessagePreview`]: preview,
  });

  return messageId;
}

export async function removeMessage(uid: string, chatId: string, messageId: string) {
  await remove(ref(db, messagePath(uid, chatId, messageId)));
}
