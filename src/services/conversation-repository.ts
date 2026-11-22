import type { LocalConversation, LocalMessage } from '../types/conversation';
import { sanitizeConversation, sortConversations } from '../utils/conversation-storage';
import { supabase } from '../utils/supabase';

export interface ConversationRepository {
  listConversations(): Promise<LocalConversation[]>;
  createConversation(conversation: LocalConversation): Promise<void>;
  updateConversation(conversationId: string, values: { title?: string; updatedAt?: string }): Promise<void>;
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

const throwIfError = (error: { message: string } | null) => {
  if (error) throw new Error(`Conversation persistence failed: ${error.message}`);
};

const mapMessage = (row: MessageRow): LocalMessage | null => {
  const metadata = row.metadata && typeof row.metadata === 'object'
    ? row.metadata as Record<string, unknown>
    : {};
  if (row.role === 'user' && typeof row.text === 'string') {
    return {
      id: row.id,
      role: 'user',
      text: row.text,
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
    return { id: row.id, role: 'assistant', response: row.response as Extract<LocalMessage, { role: 'assistant' }>['response'], createdAt: row.created_at };
  }
  return null;
};

export class SupabaseConversationRepository implements ConversationRepository {
  async listConversations(): Promise<LocalConversation[]> {
    const conversationsResult = await supabase
      .from('conversations')
      .select('id, title, created_at, updated_at, server_conversation_id')
      .order('updated_at', { ascending: false });
    throwIfError(conversationsResult.error);
    const conversationRows = (conversationsResult.data ?? []) as ConversationRow[];
    if (!conversationRows.length) return [];

    const messagesResult = await supabase
      .from('conversation_messages')
      .select('id, conversation_id, role, text, response, metadata, created_at')
      .in('conversation_id', conversationRows.map((row) => row.id))
      .order('created_at', { ascending: true });
    throwIfError(messagesResult.error);
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

  async createConversation(conversation: LocalConversation): Promise<void> {
    const safe = sanitizeConversation(conversation);
    const { error } = await supabase.from('conversations').upsert({
      id: safe.id,
      title: safe.title,
      created_at: safe.createdAt,
      updated_at: safe.updatedAt,
      server_conversation_id: safe.serverConversationId,
    }, { onConflict: 'id', ignoreDuplicates: true });
    throwIfError(error);
  }

  async updateConversation(conversationId: string, values: { title?: string; updatedAt?: string }): Promise<void> {
    const { error } = await supabase.from('conversations').update({
      ...(values.title !== undefined ? { title: values.title } : {}),
      ...(values.updatedAt !== undefined ? { updated_at: values.updatedAt } : {}),
    }).eq('id', conversationId);
    throwIfError(error);
  }

  async appendMessage(conversationId: string, message: LocalMessage): Promise<void> {
    const safe = sanitizeConversation({
      id: conversationId, title: '', createdAt: message.createdAt,
      updatedAt: message.createdAt, serverConversationId: null, messages: [message],
    }).messages[0];
    const { error } = await supabase.from('conversation_messages').upsert({
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
    }, { onConflict: 'id', ignoreDuplicates: true });
    throwIfError(error);
  }

  async deleteConversation(conversationId: string): Promise<void> {
    const { error } = await supabase.from('conversations').delete().eq('id', conversationId);
    throwIfError(error);
  }

  async setServerConversationId(conversationId: string, serverConversationId: string): Promise<void> {
    const { error } = await supabase.from('conversations')
      .update({ server_conversation_id: serverConversationId })
      .eq('id', conversationId);
    throwIfError(error);
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
  onMigrationStart: () => void = () => undefined,
) => {
  let conversations = await repository.listConversations();
  if (
    migrationState === 'complete'
    || !localConversations.length
    || (conversations.length > 0 && migrationState !== 'in_progress')
  ) {
    return { conversations, migrated: false };
  }
  onMigrationStart();
  await importConversations(repository, localConversations);
  conversations = await repository.listConversations();
  return { conversations, migrated: true };
};
