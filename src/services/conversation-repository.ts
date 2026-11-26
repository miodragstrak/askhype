import type { LocalConversation, LocalMessage } from '../types/conversation';
import { sanitizeConversation, sortConversations } from '../utils/conversation-storage';
import { HistoryError } from './history-diagnostics';
import { supabase } from '../utils/supabase';

export interface ConversationRepository {
  listConversations(): Promise<LocalConversation[]>;
  createConversation(conversation: LocalConversation): Promise<void>;
  updateConversation(conversationId: string, values: { title?: string; updatedAt?: string; serverConversationId?: string | null }): Promise<void>;
  appendMessage(conversationId: string, message: LocalMessage): Promise<void>;
  deleteConversation(conversationId: string): Promise<void>;
  setServerConversationId(conversationId: string, serverConversationId: string): Promise<void>;
}

type ConversationRow = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  server_conversation_id: string | null;
};

type MessageRow = {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  text: string | null;
  response: unknown;
  metadata: unknown;
  created_at: string;
};

const throwIfError = (result: { error: { code?: string } | null; status: number }) => {
  if (!result.error) return;
  if (result.status === 401) throw new HistoryError('authentication');
  if (result.status === 403 || result.error.code === '42501') throw new HistoryError('authorization');
  if (result.status === 0) throw new HistoryError('network');
  throw new HistoryError('persistence');
};

export const HISTORY_PAGE_SIZE = 30;

const mapMessage = (row: MessageRow): LocalMessage | null => {
  const metadata = row.metadata && typeof row.metadata === 'object'
    ? row.metadata as Record<string, unknown>
    : {};
  if (row.role === 'user' && typeof row.text === 'string') {
    return {
      id: row.id,
      role: 'user',
      text: row.text,
      ...(metadata.ordinary_turn === true ? { ordinaryTurn: true } : {}),
      ...(Array.isArray(metadata.imagePreviews) ? { imagePreviews: [] } : {}),
      ...(typeof metadata.documentName === 'string' ? { documentName: metadata.documentName } : {}),
      ...(typeof metadata.documentType === 'string' ? { documentType: metadata.documentType } : {}),
      ...(typeof metadata.documentAction === 'string'
        ? { documentAction: metadata.documentAction as Extract<LocalMessage, { role: 'user' }>['documentAction'] }
        : {}),
      createdAt: row.created_at,
    };
  }
  if (row.role === 'assistant' && row.response && typeof row.response === 'object') {
    return { id: row.id, role: 'assistant', response: row.response as Extract<LocalMessage, { role: 'assistant' }>['response'], createdAt: row.created_at,
      ...(typeof metadata.ordinary_turn_id === 'string' ? { ordinaryTurnId: metadata.ordinary_turn_id } : {}) };
  }
  return null;
};

export function historyCursor(column: 'updated_at' | 'created_at', timestamp: string, id: string) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(timestamp) ||
      !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) {
    throw new HistoryError('persistence');
  }
  return `${column}.lt.${timestamp},and(${column}.eq.${timestamp},id.lt.${id})`;
}

export class SupabaseConversationRepository implements ConversationRepository {
  private readonly scope: () => { token: string; signal: AbortSignal };
  private readonly paged: boolean;
  constructor(scope: () => { token: string; signal: AbortSignal }, paged = false) {
    this.scope = scope;
    this.paged = paged;
  }

  private authorize<T extends {
    setHeader(name: string, value: string): T;
    abortSignal(signal: AbortSignal): T;
  }>(query: T): T {
    const { token, signal } = this.scope();
    if (signal.aborted) throw new HistoryError('stale');
    return query.setHeader('Authorization', `Bearer ${token}`).abortSignal(signal);
  }

  async listConversations(): Promise<LocalConversation[]> {
    if (this.paged) return (await this.listConversationPage()).items;
    const conversationsResult = await this.authorize(supabase
      .from('conversations')
      .select('id, title, created_at, updated_at, server_conversation_id')
      .order('updated_at', { ascending: false }).order('id', { ascending: false }));
    throwIfError(conversationsResult);
    const conversationRows = (conversationsResult.data ?? []) as ConversationRow[];
    if (!conversationRows.length) return [];

    const messagesResult = await this.authorize(supabase
      .from('conversation_messages')
      .select('id, conversation_id, role, text, response, metadata, created_at')
      .in('conversation_id', conversationRows.map((row) => row.id))
      .order('created_at', { ascending: true }).order('id', { ascending: true }));
    throwIfError(messagesResult);
    const messageRows = (messagesResult.data ?? []) as MessageRow[];

    return sortConversations(conversationRows.map((row) => ({
      id: row.id,
      title: row.title,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      serverConversationId: row.server_conversation_id,
      messages: messageRows
        .filter((message) => message.conversation_id === row.id)
        .map(mapMessage)
        .filter((message): message is LocalMessage => message !== null),
    })));
  }

  async listConversationPage(cursor?: LocalConversation) {
    const query = supabase.from('conversations')
      .select('id, title, created_at, updated_at, server_conversation_id')
      .order('updated_at', { ascending: false }).order('id', { ascending: false })
      .limit(HISTORY_PAGE_SIZE + 1);
    if (cursor) query.or(historyCursor('updated_at', cursor.updatedAt, cursor.id));
    const result = await this.authorize(query);
    throwIfError(result);
    const rows = (result.data ?? []) as ConversationRow[];
    return {
      items: rows.slice(0, HISTORY_PAGE_SIZE).map((row): LocalConversation => ({
        id: row.id, title: row.title, createdAt: row.created_at, updatedAt: row.updated_at,
        serverConversationId: row.server_conversation_id, messages: [],
      })),
      more: rows.length > HISTORY_PAGE_SIZE,
    };
  }

  async listMessagePage(conversationId: string, cursor?: LocalMessage) {
    const query = supabase.from('conversation_messages')
      .select('id, conversation_id, role, text, response, metadata, created_at')
      .eq('conversation_id', conversationId)
      .order('created_at', { ascending: false }).order('id', { ascending: false })
      .limit(HISTORY_PAGE_SIZE + 1);
    if (cursor) query.or(historyCursor('created_at', cursor.createdAt, cursor.id));
    const result = await this.authorize(query);
    throwIfError(result);
    const rows = (result.data ?? []) as MessageRow[];
    return {
      items: rows.slice(0, HISTORY_PAGE_SIZE).reverse().map(mapMessage)
        .filter((message): message is LocalMessage => message !== null),
      more: rows.length > HISTORY_PAGE_SIZE,
    };
  }

  async createConversation(conversation: LocalConversation): Promise<void> {
    const safe = sanitizeConversation(conversation);
    const result = await this.authorize(supabase.from('conversations').upsert({
      id: safe.id,
      title: safe.title,
      created_at: safe.createdAt,
      updated_at: safe.updatedAt,
      server_conversation_id: safe.serverConversationId,
    }, { onConflict: 'id', ignoreDuplicates: true }));
    throwIfError(result);
  }

  async updateConversation(conversationId: string, values: { title?: string; updatedAt?: string; serverConversationId?: string | null }): Promise<void> {
    const result = await this.authorize(supabase.from('conversations').update({
      ...(values.serverConversationId !== undefined ? { server_conversation_id: values.serverConversationId } : {}),
      ...(values.title !== undefined ? { title: values.title } : {}),
      ...(values.updatedAt !== undefined ? { updated_at: values.updatedAt } : {}),
    }).eq('id', conversationId).select('id')).maybeSingle();
    throwIfError(result);
    if (!result.data) throw new HistoryError('missing');
  }

  async appendMessage(conversationId: string, message: LocalMessage): Promise<void> {
    const safe = sanitizeConversation({
      id: conversationId, title: '', createdAt: message.createdAt,
      updatedAt: message.createdAt, serverConversationId: null, messages: [message],
    }).messages[0];
    const result = await this.authorize(supabase.from('conversation_messages').upsert({
      id: safe.id,
      conversation_id: conversationId,
      role: safe.role,
      text: safe.role === 'user' ? safe.text : null,
      response: safe.role === 'assistant' ? safe.response : null,
      metadata: safe.role === 'user' ? {
        documentName: safe.documentName,
        documentType: safe.documentType,
        documentAction: safe.documentAction,
      } : {},
      created_at: safe.createdAt,
    }, { onConflict: 'id', ignoreDuplicates: true }));
    throwIfError(result);
  }

  async deleteConversation(conversationId: string): Promise<void> {
    const result = await this.authorize(supabase.from('conversations').delete().eq('id', conversationId));
    throwIfError(result);
  }

  async setServerConversationId(conversationId: string, serverConversationId: string): Promise<void> {
    const result = await this.authorize(supabase.from('conversations')
      .update({ server_conversation_id: serverConversationId })
      .eq('id', conversationId));
    throwIfError(result);
  }
}

export const importConversations = async (
  repository: ConversationRepository,
  conversations: LocalConversation[],
) => {
  for (const conversation of conversations) {
    await repository.createConversation(conversation);
    for (const message of conversation.messages) {
      await repository.appendMessage(conversation.id, message);
    }
  }
};

export const initializeAuthenticatedHistory = async (
  repository: ConversationRepository,
  localConversations: LocalConversation[],
  migrationState: 'complete' | 'in_progress' | null,
  onMigrationStart: () => void | false = () => undefined,
) => {
  let conversations = await repository.listConversations();
  if (
    migrationState === 'complete'
    || !localConversations.length
    || (conversations.length > 0 && migrationState !== 'in_progress')
  ) {
    return { conversations, migrated: false };
  }
  if (onMigrationStart() === false) return { conversations, migrated: false };
  await importConversations(repository, localConversations);
  conversations = await repository.listConversations();
  return { conversations, migrated: true };
};
