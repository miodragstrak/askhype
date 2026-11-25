import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { ResearchProgress } from './ResearchProgress';
import type { ResearchJob } from '../../types/chat';

const job: ResearchJob = {
  research_id: 'test', status: 'running', query: 'International trade',
  created_at: '2026-11-25T10:00:00Z', updated_at: '2026-11-25T10:02:34Z',
};

it('shows only verified running status and the research question', () => {
  const html = renderToStaticMarkup(<ResearchProgress job={job} />);
  expect(html).toContain('International trade');
  expect(html).toContain('Istraživanje je u toku');
  expect(html).toContain('Detaljno istraživanje može trajati nekoliko minuta.');
});

it('shows the persisted elapsed time and a safe terminal error', () => {
  const html = renderToStaticMarkup(<ResearchProgress job={{ ...job, status: 'failed', failure_category: 'provider_timeout' }} />);
  expect(html).toContain('02:34');
  expect(html).toContain('istraživanje je isteklo');
});
