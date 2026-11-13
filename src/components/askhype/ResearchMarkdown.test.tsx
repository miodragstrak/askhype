import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { ResearchSource } from '../../types/chat';
import { ResearchMarkdown } from './ResearchMarkdown';
import { cleanResearchSourceLabel } from './research-display';

const sources: ResearchSource[] = [
  {
    title: 'OpenAI', display_label: 'openai.com',
    url: 'https://vertexaisearch.cloud.google.com/grounding-api-redirect/source-one',
    citation_ids: [1],
  },
  {
    title: 'Anthropic', display_label: 'anthropic.com',
    url: 'https://anthropic.com/research/agents', citation_ids: [2, 4],
  },
];

const render = (text: string) => renderToStaticMarkup(<ResearchMarkdown text={text} sources={sources} />);

describe('ResearchMarkdown', () => {
  it('renders one mapped citation with its exact provider href', () => {
    const html = render('Tvrdnja [cite: 1].');
    expect(html).toContain('href="https://vertexaisearch.cloud.google.com/grounding-api-redirect/source-one"');
    expect(html).toContain('>[1]</a>');
  });

  it('renders multiple mapped citations as separate links', () => {
    const html = render('Tvrdnja [cite: 1, 2].');
    expect(html).toContain('>[1]</a>');
    expect(html).toContain('>[2]</a>');
    expect(html).toContain('href="https://anthropic.com/research/agents"');
  });

  it('keeps an unmapped citation neutral and never links it to another source', () => {
    const html = render('Nepodržano [cite: 9].');
    expect(html).toContain('[9]');
    expect(html).not.toContain('source-one');
    expect(html).not.toContain('anthropic.com/research');
  });

  it('renders Markdown headings and lists', () => {
    const html = render('## Naslov\n\n- Prva\n- Druga');
    expect(html).toContain('<h4');
    expect(html).toContain('Naslov</h4>');
    expect(html).toContain('<ul');
    expect(html).toContain('<li>Prva</li>');
  });

  it('renders GFM tables inside a responsive scrolling wrapper', () => {
    const html = render('| Model | Status |\n|---|---|\n| Agent | Aktivan |');
    expect(html).toContain('overflow-x-auto');
    expect(html).toContain('<table');
    expect(html).toContain('<th');
    expect(html).toContain('<td');
  });

  it('does not execute or render raw HTML and blocks unsafe links', () => {
    const html = render('<script>alert(1)</script> [klik](javascript:alert(1))');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('href="javascript:');
  });

  it('preserves clean source labels from ASK-DR-002A', () => {
    expect(cleanResearchSourceLabel(sources[0], 1)).toBe('openai.com');
    expect(cleanResearchSourceLabel({ title: '', url: sources[0].url }, 3)).toBe('Izvor 3');
  });
});
