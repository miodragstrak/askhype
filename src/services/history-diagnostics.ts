type HistoryCategory = 'authentication' | 'authorization' | 'network' | 'persistence' | 'cache' | 'stale' | 'missing';
type HistoryOperation = 'auth_transition' | 'hydrate' | 'order' | 'open' | 'create' | 'save_user'
  | 'save_assistant' | 'update' | 'delete' | 'save_retry' | 'accept_response';

export class HistoryError extends Error {
  readonly category: HistoryCategory;
  constructor(category: HistoryCategory) {
    super('Conversation history operation failed.');
    this.category = category;
  }
}

export const historyDiagnostic = (
  operation: HistoryOperation,
  auth: 'account' | 'guest' | 'loading',
  conversationId?: string,
) => {
  const start = performance.now();
  const correlationId = globalThis.crypto?.randomUUID?.() ?? String(start);
  return (category?: HistoryCategory) => {
    const safeId = conversationId && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(conversationId)
      ? conversationId : undefined;
    const data = { correlationId, operation, auth, conversationId: safeId,
      outcome: category ? 'failed' : 'success', category, durationMs: Math.round(performance.now() - start) };
    if (category) console.warn('askhype_history', data);
    else console.info('askhype_history', data);
  };
};

export const historyErrorCategory = (error: unknown): HistoryCategory =>
  error instanceof HistoryError ? error.category : error instanceof TypeError ? 'network' : 'persistence';
