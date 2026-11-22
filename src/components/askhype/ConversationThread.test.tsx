import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { ChatResponse } from '../../types/chat';
import { ConversationThread } from './ConversationThread';

const response: ChatResponse = {
  conversation_id: 'language-test',
  provider: 'mock',
  answer_type: 'answer',
  summary: 'Glavni odgovor je završen.',
  recommendations: [],
  follow_up_actions: ['Prvo pitanje', 'Drugo pitanje', 'Treće pitanje', 'Četvrto pitanje'],
  sources: [],
  generated_at: '2026-11-22T12:00:00Z',
};

const renderThread = (loading: boolean) => renderToStaticMarkup(
  <ConversationThread
    messages={[{ id: 'assistant-1', role: 'assistant', response, createdAt: response.generated_at }]}
    loading={loading}
    error={null}
    quota={null}
    onRetry={() => {}}
    onFollowUp={() => {}}
    onSignIn={() => {}}
    onSignUp={() => {}}
    onPremium={() => {}}
  />,
);

describe('follow-up completion timing', () => {
  it('hides follow-up suggestions while the assistant response is loading', () => {
    const html = renderThread(true);
    expect(html).toContain('Glavni odgovor je završen.');
    expect(html).not.toContain('Predložena dodatna pitanja');
    expect(html).not.toContain('Prvo pitanje');
  });

  it('shows no more than three secondary suggestions after completion', () => {
    const html = renderThread(false);
    expect(html).toContain('Predložena dodatna pitanja');
    expect(html).toContain('Prvo pitanje');
    expect(html).toContain('Drugo pitanje');
    expect(html).toContain('Treće pitanje');
    expect(html).not.toContain('Četvrto pitanje');
    expect(html.indexOf('Glavni odgovor je završen.')).toBeLessThan(html.indexOf('Predložena dodatna pitanja'));
  });
});
