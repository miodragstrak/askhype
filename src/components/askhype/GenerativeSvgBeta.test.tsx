import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { sendGenerativeSvgAnimation } from '../../services/chat-api';
import type { ChatResponse } from '../../types/chat';
import { saveConversations } from '../../utils/conversation-storage';
import { ConversationThread } from './ConversationThread';
import { GenerativeSvgPreview } from './GenerativeSvgPreview';
import previewSource from './GenerativeSvgPreview.tsx?raw';
import composerSource from './PromptComposer.tsx?raw';
import { PromptComposer } from './PromptComposer';

afterEach(() => vi.unstubAllGlobals());

describe('Generative SVG beta', () => {
  it('renders SVG only in a sandboxed CSP iframe without React HTML injection', () => {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="10" cy="10" r="5"/></svg>';
    const html = renderToStaticMarkup(<GenerativeSvgPreview svg={svg} remaining={3}/>);
    expect(html).toContain('<iframe');
    expect(html).toContain('sandbox=""');
    expect(html).toContain('Content-Security-Policy');
    expect(html).toContain('default-src &#x27;none&#x27;');
    expect(html).toContain('Preostalo animacija danas: 3');
    expect(previewSource).not.toContain('dangerouslySetInnerHTML');
  });

  it('shows the beta action and renders loading/result states', () => {
    const composer = renderToStaticMarkup(<PromptComposer onSubmit={async () => true}/>);
    expect(composer).toContain('AI Animation');
    expect(composer).toContain('Beta');
    const response: ChatResponse = {
      conversation_id: 'svg_1', provider: 'gemini', answer_type: 'generative_svg_animation',
      summary: 'AI animacija je spremna.', recommendations: [], follow_up_actions: [], sources: [],
      generated_at: new Date().toISOString(), generative_svg: '<svg xmlns="http://www.w3.org/2000/svg"/>',
      animation_quota_remaining: 2,
    };
    const thread = renderToStaticMarkup(<ConversationThread
      messages={[{ id: 'a', role: 'assistant', response, createdAt: response.generated_at }]}
      loading loadingLabel="AskHype kreira animaciju…" error={null} quota={null}
      onRetry={() => {}} onFollowUp={() => {}} onSignIn={() => {}} onSignUp={() => {}} onPremium={() => {}}
    />);
    expect(thread).toContain('AskHype kreira animaciju…');
    expect(thread).toContain('title="AI animacija"');
  });

  it('keeps the reference backend contract but hides reference upload from beta UI', () => {
    expect(composerSource).toContain("documentAction !== 'animation'");
    expect(composerSource).toContain('AI animacije su u beta verziji. Rezultati mogu da variraju.');
    expect(composerSource).not.toContain('Opcionalno: dodajte sliku kao vizuelnu referencu');
    expect(composerSource).not.toContain('Dodaj referentnu sliku');
  });

  it('sends prompt-only and reference requests as multipart data', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ svg: '<svg/>', has_reference: true, generation_seconds: 1, attempts: 1, remaining_quota: 4, generated_at: new Date().toISOString() }),
    });
    vi.stubGlobal('fetch', fetchMock);
    await sendGenerativeSvgAnimation('Noćna scena', 20, { accessToken: 'token' });
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.method).toBe('POST');
    expect((options.body as FormData).get('prompt')).toBe('Noćna scena');
    expect((options.body as FormData).get('duration_seconds')).toBe('20');
    expect((options.headers as Record<string, string>).Authorization).toBe('Bearer token');
  });

  it('does not persist generated SVG content in conversation history', () => {
    let stored = '';
    vi.stubGlobal('localStorage', {
      setItem: (_key: string, value: string) => { stored = value; }, getItem: () => null,
      removeItem: () => {}, clear: () => {}, key: () => null, length: 0,
    });
    saveConversations([{ id: 'c', title: 'Animacija', createdAt: '2026-01-01', updatedAt: '2026-01-01', serverConversationId: null, messages: [
      { id: 'm', role: 'assistant', createdAt: '2026-01-01', response: {
        conversation_id: 'x', provider: 'gemini', answer_type: 'generative_svg_animation', summary: 'Spremna',
        recommendations: [], follow_up_actions: [], sources: [], generated_at: '2026-01-01', generative_svg: '<svg>PRIVATE</svg>',
        generative_svg_storyboard: { title: 'Private', total_duration_seconds: 10, generation_seconds: 1, remaining_quota: 1, generated_at: '2026-01-01', scenes: [{ id: 'scene_1', duration_seconds: 10, transition_in: 'fade', transition_out: 'fade', svg: '<svg>STORYBOARD_PRIVATE</svg>' }] },
      } },
    ] }]);
    expect(stored).not.toContain('PRIVATE');
    const persisted = JSON.parse(stored);
    expect(persisted[0].messages[0].response.generative_svg).toBeUndefined();
    expect(persisted[0].messages[0].response.generative_svg_storyboard).toBeUndefined();
  });
});
