import type { LocalConversation, LocalMessage } from '../types/conversation';

const STORAGE_KEY = 'askhype:conversations:v1';

const isMessage = (value: unknown): value is LocalMessage => {
  if (!value || typeof value !== 'object') return false;
  const message = value as Partial<LocalMessage>;
  if (typeof message.id !== 'string' || typeof message.createdAt !== 'string') return false;
  if (message.role === 'user') return typeof message.text === 'string';
  return message.role === 'assistant' && Boolean(message.response && typeof message.response === 'object');
};

const isConversation = (value: unknown): value is LocalConversation => {
  if (!value || typeof value !== 'object') return false;
  const conversation = value as Partial<LocalConversation>;
  return (
    typeof conversation.id === 'string' &&
    typeof conversation.title === 'string' &&
    typeof conversation.createdAt === 'string' &&
    typeof conversation.updatedAt === 'string' &&
    (conversation.serverConversationId === null || typeof conversation.serverConversationId === 'string') &&
    Array.isArray(conversation.messages) &&
    conversation.messages.every(isMessage)
  );
};

export const sortConversations = (conversations: LocalConversation[]) =>
  [...conversations].sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));

export const loadConversations = (): LocalConversation[] => {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
    return Array.isArray(parsed) ? sortConversations(parsed.filter(isConversation)) : [];
  } catch {
    return [];
  }
};

export const saveConversations = (conversations: LocalConversation[]) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sortConversations(conversations)));
  } catch {
    // The active conversation remains usable when storage is unavailable.
  }
};

export const conversationTitle = (prompt: string) => {
  const normalized = prompt.trim().replace(/\s+/g, ' ');
  return normalized.length > 52 ? `${normalized.slice(0, 49).trim()}...` : normalized;
};
