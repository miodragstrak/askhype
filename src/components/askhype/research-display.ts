import type { ResearchSource } from '../../types/chat';

const GROUNDING_REDIRECT_HOSTS = new Set([
  'vertexaisearch.cloud.google.com',
  'grounding-api-redirect.googleapis.com',
]);

const isGroundingRedirectHost = (host: string): boolean =>
  GROUNDING_REDIRECT_HOSTS.has(host) || host.includes('grounding-api-redirect');

const safeExternalUrl = (value: string): string | null => {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
};

export const cleanResearchSourceLabel = (source: ResearchSource, fallbackIndex: number): string => {
  for (const candidate of [source.display_label, source.title, source.publisher]) {
    const label = candidate?.trim();
    if (label && !/^https?:\/\//i.test(label) && !isGroundingRedirectHost(label.replace(/^www\./, ''))) return label;
  }
  if (source.original_url) {
    try {
      const host = new URL(source.original_url).hostname.replace(/^www\./, '');
      if (!isGroundingRedirectHost(host)) return host;
    } catch { /* fall through to safe fallback */ }
  }
  try {
    const host = new URL(source.url).hostname.replace(/^www\./, '');
    if (!isGroundingRedirectHost(host)) return host;
  } catch {
    // Use the stable numbered fallback below.
  }
  return `Izvor ${fallbackIndex}`;
};

const markdownDestination = (url: string): string =>
  url.replace(/\\/g, '%5C').replace(/\(/g, '%28').replace(/\)/g, '%29').replace(/\s/g, '%20');

export const replaceResearchCitations = (text: string, sources: ResearchSource[]): string =>
  text.replace(/\[cite:\s*([0-9]+(?:\s*,\s*[0-9]+)*)\]/gi, (_marker, values: string) => {
    const ids = values.split(',').map((value) => Number(value.trim()));
    return ids.map((id) => {
      const matches = sources.filter((source) => source.citation_ids?.includes(id));
      if (matches.length !== 1) return `[${id}]`;
      const href = safeExternalUrl(matches[0].url);
      if (!href) return `[${id}]`;
      return `[\\[${id}\\]](${markdownDestination(href)})`;
    }).join(' ');
  });

export const safeResearchHref = safeExternalUrl;
