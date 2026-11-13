import type { ChatResponse } from './chat';

export type LocalMessage =
  | {
      id: string;
      role: 'user';
      text: string;
      // Object URLs are page-lifetime previews only; image bytes are never persisted or resent.
      imagePreviews?: string[];
      // Display metadata only; uploaded document bytes are never persisted.
      documentName?: string;
      documentType?: string;
      documentAction?: 'analyze' | 'transform' | 'presentation' | 'research';
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
