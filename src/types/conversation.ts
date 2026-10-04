import type { ChatResponse } from './chat';

export type LocalMessage =
  | {
      id: string;
      role: 'user';
      text: string;
      createdAt: string;
    }
  | {
      id: string;
      role: 'assistant';
      response: ChatResponse;
      createdAt: string;
    };

export interface LocalConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  serverConversationId: string | null;
  messages: LocalMessage[];
}
