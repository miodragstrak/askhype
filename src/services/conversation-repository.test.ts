import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LocalConversation, LocalMessage } from '../types/conversation';
import {
  importConversations,
  initializeAuthenticatedHistory,
  type ConversationRepository,
} from './conversation-repository';
import { loadConversations, saveConversations } from '../utils/conversation-storage';

const response = {
  conversation_id: 'server-1', provider: 'gemini', answer_type: 'general', summary: 'Odgovor',
  recommendations: [], follow_up_actions: [], sources: [], generated_at: '2026-11-22T10:01:00Z',
};
const userMessage: LocalMessage = { id: '00000000-0000-4000-8000-000000000002', role: 'user', text: 'Zdravo', createdAt: '2026-11-22T10:00:00Z' };
const assistantMessage: LocalMessage = { id: '00000000-0000-4000-8000-000000000003', role: 'assistant', response, createdAt: '2026-11-22T10:01:00Z' };
const conversation = (): LocalConversation => ({
  id: '00000000-0000-4000-8000-000000000001', title: 'Zdravo',
  createdAt: '2026-11-22T10:00:00Z', updatedAt: '2026-11-22T10:01:00Z',
  serverConversationId: null, messages: [userMessage, assistantMessage],
});

class MemoryRepository implements ConversationRepository {
  conversations = new Map<string, LocalConversation>();
  fail = false;
  private check() { if (this.fail) throw new Error('offline'); }
  async listConversations() { this.check(); return [...this.conversations.values()]; }
  async createConversation(value: LocalConversation) {
    this.check();
    if (!this.conversations.has(value.id)) this.conversations.set(value.id, { ...value, messages: [] });
  }
  async updateConversation(id: string, values: { title?: string; updatedAt?: string }) {
    this.check(); const value = this.conversations.get(id); if (!value) throw new Error('missing');
    this.conversations.set(id, { ...value, title: values.title ?? value.title, updatedAt: values.updatedAt ?? value.updatedAt });
  }
  async appendMessage(id: string, message: LocalMessage) {
    this.check(); const value = this.conversations.get(id); if (!value) throw new Error('missing');
    if (!value.messages.some((item) => item.id === message.id)) {
      this.conversations.set(id, { ...value, messages: [...value.messages, message] });
    }
  }
  async deleteConversation(id: string) { this.check(); this.conversations.delete(id); }
  async setServerConversationId(id: string, serverId: string) {
    this.check(); const value = this.conversations.get(id); if (!value) throw new Error('missing');
    this.conversations.set(id, { ...value, serverConversationId: serverId });
  }
}

describe('durable conversation history', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
  });

  it('keeps guest history in localStorage', () => {
    const withTransientData: LocalConversation = {
      ...conversation(),
      messages: [
        { ...userMessage, imagePreviews: ['blob:https://example.test/image'] },
        {
          ...assistantMessage,
          response: {
            ...assistantMessage.response,
            generative_svg: '<svg />',
            download: { filename: 'report.xlsx', url: 'blob:https://example.test/file', available: true },
          },
        },
      ],
    };
    saveConversations([withTransientData]);
    expect(loadConversations()).toHaveLength(1);
    expect(loadConversations()[0].messages).toHaveLength(2);
    const stored = loadConversations()[0].messages;
    expect(stored[0]).not.toHaveProperty('imagePreviews');
    expect(stored[1]).not.toHaveProperty('response.generative_svg');
    expect(stored[1]).not.toHaveProperty('response.download.url');
  });

  it('loads authenticated server history', async () => {
    const repository = new MemoryRepository();
    await importConversations(repository, [conversation()]);
    const result = await initializeAuthenticatedHistory(repository, [], 'complete');
    expect(result.conversations[0].messages).toHaveLength(2);
    expect(result.migrated).toBe(false);
  });

  it('imports local history once when the server is empty', async () => {
    const repository = new MemoryRepository();
    const first = await initializeAuthenticatedHistory(repository, [conversation()], null);
    const second = await initializeAuthenticatedHistory(repository, [conversation()], 'complete');
    expect(first.migrated).toBe(true);
    expect(second.migrated).toBe(false);
    expect(second.conversations).toHaveLength(1);
    expect(second.conversations[0].messages).toHaveLength(2);
  });

  it('does not import local history into a non-empty server account', async () => {
    const repository = new MemoryRepository();
    await importConversations(repository, [conversation()]);
    const other = { ...conversation(), id: '00000000-0000-4000-8000-000000000010' };
    const result = await initializeAuthenticatedHistory(repository, [other], null);
    expect(result.conversations.map((item) => item.id)).toEqual([conversation().id]);
  });

  it('supports append, metadata update, deletion and cross-device reads', async () => {
    const repository = new MemoryRepository();
    const empty = { ...conversation(), messages: [] };
    await repository.createConversation(empty);
    await repository.appendMessage(empty.id, userMessage);
    await repository.appendMessage(empty.id, assistantMessage);
    await repository.setServerConversationId(empty.id, 'server-1');
    const secondDevice = await repository.listConversations();
    expect(secondDevice[0].messages.map((message) => message.role)).toEqual(['user', 'assistant']);
    expect(secondDevice[0].serverConversationId).toBe('server-1');
    await repository.deleteConversation(empty.id);
    expect(await repository.listConversations()).toEqual([]);
  });

  it('keeps the in-memory UI state intact when persistence fails', async () => {
    const repository = new MemoryRepository();
    const visible = [conversation()];
    repository.fail = true;
    await expect(repository.createConversation(conversation())).rejects.toThrow('offline');
    expect(visible).toEqual([conversation()]);
  });

  it('does not select an active conversation that is absent from server history', async () => {
    const repository = new MemoryRepository();
    const result = await initializeAuthenticatedHistory(repository, [], 'complete');
    const activeId = result.conversations.find((item) => item.id === 'missing')?.id ?? null;
    expect(activeId).toBeNull();
  });

  it('resumes an interrupted migration without duplicating rows', async () => {
    const repository = new MemoryRepository();
    await repository.createConversation({ ...conversation(), messages: [] });
    await repository.appendMessage(conversation().id, userMessage);
    const result = await initializeAuthenticatedHistory(repository, [conversation()], 'in_progress');
    expect(result.conversations).toHaveLength(1);
    expect(result.conversations[0].messages).toEqual([userMessage, assistantMessage]);
  });
});
