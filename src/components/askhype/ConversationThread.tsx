import { Download, ExternalLink, FileText, Loader2, LockKeyhole, MapPin, RefreshCcw } from 'lucide-react';
import type { ReactNode } from 'react';
import type { QuotaLimitPayload } from '../../services/chat-api';
import type { ChatResponse, ResearchSource } from '../../types/chat';
import type { LocalMessage } from '../../types/conversation';

interface ConversationThreadProps {
  messages: LocalMessage[];
  loading: boolean;
  error: string | null;
  quota: QuotaLimitPayload | null;
  onRetry: () => void;
  onFollowUp: (prompt: string) => void;
  onSignIn: () => void;
  onSignUp: () => void;
  onPremium: () => void;
}

const hypeSourceOwner = (url: string): string | null => {
  try {
    const source = new URL(url);
    if (!['https:', 'http:'].includes(source.protocol)) return null;
    const host = source.hostname.replace(/^www\./, '');
    if (host === 'hypetv.rs') return 'Hype TV';
    if (host === 'hypeproduction.rs') return 'Hype Production';
  } catch {
    return null;
  }
  return null;
};

const cleanResearchSourceLabel = (source: ResearchSource): string => {
  const title = source.title.trim();
  if (title && !/^https?:\/\//i.test(title) && !title.includes('grounding-api-redirect')) return title;
  const publisher = source.publisher?.trim();
  if (publisher && !publisher.includes('grounding-api-redirect')) return publisher.replace(/^www\./, '');
  try {
    const host = new URL(source.url).hostname.replace(/^www\./, '');
    return host.includes('grounding-api-redirect') ? 'Google izvor' : host;
  } catch {
    return 'Izvor';
  }
};

const renderResearchText = (text: string, sources: ResearchSource[]): ReactNode[] => {
  const citationPattern = /\[cite:\s*([0-9]+(?:\s*,\s*[0-9]+)*)\]/gi;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(citationPattern)) {
    const index = match.index ?? 0;
    if (index > cursor) nodes.push(text.slice(cursor, index));
    const ids = match[1].split(',').map((value) => Number(value.trim()));
    nodes.push(...ids.map((id) => {
      const matches = sources.filter((source) => source.citation_ids.includes(id));
      if (matches.length !== 1) return <span key={`${index}-${id}`}>[cite: {id}]</span>;
      const source = matches[0];
      return (
        <a key={`${index}-${id}`} href={source.url} target="_blank" rel="noreferrer"
          aria-label={`Otvori izvor ${id}: ${cleanResearchSourceLabel(source)}`}
          className="mx-0.5 inline-flex rounded px-1 text-xs font-semibold text-hype-blue underline decoration-chat-outline underline-offset-2 focus:outline-none focus:ring-2 focus:ring-hype-yellow">
          [{id}]
        </a>
      );
    }));
    cursor = index + match[0].length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
};

const AssistantResponse = ({
  response,
  onFollowUp,
  disabled,
}: {
  response: ChatResponse;
  onFollowUp: (prompt: string) => void;
  disabled: boolean;
}) => {
  const researchSections = response.research?.sections.filter((section, index) => {
    if (index !== 0) return true;
    const summary = response.research?.summary.replace(/\s+/g, ' ').trim();
    const content = section.content.replace(/\s+/g, ' ').trim();
    return content !== summary;
  });
  return (
  <div className="space-y-5 lg:space-y-6">
    {!response.research && <p className="whitespace-pre-wrap text-[15px] leading-7 text-chat-text">{response.summary}</p>}

    {response.research ? (
      <div className="space-y-6">
        <h2 className="text-xl font-semibold text-chat-text">{response.research.title}</h2>
        <section className="space-y-2">
          <h3 className="text-base font-semibold text-chat-text">Kratak odgovor</h3>
          <p className="whitespace-pre-wrap text-[15px] leading-7 text-chat-text">{renderResearchText(response.research.summary, response.research.sources)}</p>
        </section>
        <section className="space-y-4">
          <h3 className="text-base font-semibold text-chat-text">Detaljno istraživanje</h3>
          {researchSections?.map((section, index) => (
            <div key={`${section.heading}-${index}`} className="space-y-2">
              <h4 className="text-sm font-semibold text-chat-text">{section.heading}</h4>
              <p className="whitespace-pre-wrap text-sm leading-7 text-chat-text">{renderResearchText(section.content, response.research!.sources)}</p>
            </div>
          ))}
        </section>
        {response.research.sources.length > 0 && (
          <section className="space-y-3">
            <h3 className="text-base font-semibold text-chat-text">Izvori</h3>
            <ol className="space-y-2 text-xs text-chat-muted">
              {response.research.sources.map((source, index) => (
                <li key={source.url} className="flex gap-2">
                  <span className="w-8 flex-none text-right">{source.citation_ids.length ? source.citation_ids.join(',') : index + 1}.</span>
                  <a href={source.url} target="_blank" rel="noreferrer"
                    className="inline-flex min-w-0 items-center gap-1 underline decoration-chat-outline underline-offset-4 hover:text-chat-text">
                    <span className="truncate">{cleanResearchSourceLabel(source)}</span><ExternalLink size={11} className="flex-none" />
                  </a>
                </li>
              ))}
            </ol>
          </section>
        )}
        {response.research.limitations.length > 0 ? (
          <div className="rounded-lg border border-chat-border bg-chat-elevated p-3 text-xs leading-5 text-chat-muted">
            <span className="font-semibold text-chat-text">Ograničenja: </span>
            {response.research.limitations.join(' ')}
          </div>
        ) : null}
        {typeof response.research_quota_remaining === 'number' && (
          <p className="text-[11px] text-chat-muted">Preostalo Deep Research zahteva danas: {response.research_quota_remaining}</p>
        )}
      </div>
    ) : null}

    {response.answer_type === 'presentation_generation' && response.presentation_slide_count ? (
      <p className="text-xs font-medium text-chat-muted">Broj slajdova: {response.presentation_slide_count}</p>
    ) : null}

    {response.download && (response.download.url ? (
      <a href={response.download.url} download={response.download.filename} className="inline-flex items-center gap-2 rounded-full bg-hype-blue px-4 py-2 text-sm font-semibold text-white focus:outline-none focus:ring-2 focus:ring-hype-yellow">
        <Download size={16} /> {response.answer_type === 'presentation_generation' ? 'Preuzmi PowerPoint' : 'Preuzmi Excel'}
      </a>
    ) : (
      <p className="text-xs text-chat-muted">Preuzimanje više nije dostupno nakon ponovnog učitavanja. Ponovi generisanje za novi fajl.</p>
    ))}

    {response.recommendations.length > 0 && (
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-1 lg:grid-cols-2 lg:gap-4">
        {response.recommendations.map((recommendation) => (
          <article key={recommendation.id} className="rounded-lg border border-chat-border bg-chat-elevated p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-hype-yellow">{recommendation.category}</p>
                <h3 className="mt-1 text-base font-semibold leading-6 text-chat-text">
                  {recommendation.title}
                </h3>
              </div>
              {recommendation.source_url && (
                <a
                  href={recommendation.source_url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`Otvori izvor za ${recommendation.title}`}
                  title="Otvori izvor"
                  className="inline-flex h-9 w-9 flex-none items-center justify-center rounded-md text-chat-muted hover:bg-chat-hover hover:text-chat-text focus:outline-none focus:ring-2 focus:ring-hype-yellow"
                >
                  <ExternalLink size={16} />
                </a>
              )}
            </div>
            <p className="mt-2 text-sm leading-6 text-chat-muted">{recommendation.short_description}</p>
            <div className="mt-3 flex items-start gap-2 text-xs text-chat-muted">
              <MapPin size={14} className="mt-0.5 flex-none" />
              <span>{recommendation.location}</span>
            </div>
            {(recommendation.estimated_price || recommendation.date_or_duration) && (
              <p className="mt-2 text-xs font-medium text-chat-muted">
                {[recommendation.estimated_price, recommendation.date_or_duration].filter(Boolean).join(' · ')}
              </p>
            )}
            <p className="mt-3 border-t border-chat-border pt-3 text-sm leading-6 text-chat-text">
              {recommendation.reason}
            </p>
          </article>
        ))}
      </div>
    )}

    {!response.research && response.sources.length > 0 && (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-chat-muted">
        <span className="font-semibold text-chat-text">Izvori</span>
        {response.sources.map((source) =>
          source.url ? (
            <a
              key={`${source.title}-${source.url}`}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex max-w-full flex-wrap items-center gap-1 underline decoration-chat-outline underline-offset-4 hover:text-chat-text"
            >
              {source.title}
              <ExternalLink size={11} />
              {hypeSourceOwner(source.url) ? (
                <span className="rounded bg-hype-blue px-1.5 py-0.5 text-[10px] font-semibold text-chat-source no-underline ring-1 ring-inset ring-chat-source-border">
                  {hypeSourceOwner(source.url)}
                </span>
              ) : response.answer_type === 'hype_content' ? (
                <span className="text-[10px] text-chat-muted">Spoljni izvor</span>
              ) : null}
            </a>
          ) : (
            <span key={source.title}>{source.title}</span>
          ),
        )}
      </div>
    )}

    {response.follow_up_actions.length > 0 && (
      <div className="flex flex-wrap gap-2">
        {response.follow_up_actions.map((action) => (
          <button
            key={action}
            type="button"
            disabled={disabled}
            onClick={() => onFollowUp(action)}
            className="min-h-9 rounded-full border border-chat-outline bg-chat-elevated px-3 py-1.5 text-left text-xs font-medium text-chat-text transition enabled:hover:bg-chat-hover focus:outline-none focus:ring-2 focus:ring-hype-yellow disabled:cursor-not-allowed disabled:border-chat-border disabled:text-chat-muted"
          >
            {action}
          </button>
        ))}
      </div>
    )}
  </div>
  );
};

const QuotaNotice = ({
  quota,
  onSignIn,
  onSignUp,
  onPremium,
}: Pick<ConversationThreadProps, 'quota' | 'onSignIn' | 'onSignUp' | 'onPremium'>) => {
  if (!quota) return null;
  const guest = quota.plan === 'guest';

  return (
    <div className="flex gap-3 border-l-2 border-hype-yellow py-2 pl-4">
      <LockKeyhole size={18} className="mt-1 flex-none text-chat-text" />
      <div>
        <p className="text-sm font-semibold text-chat-text">Dostigao si limit pitanja.</p>
        <p className="mt-1 text-sm leading-6 text-chat-muted">
          Iskorišćeno je {quota.used} od {quota.limit} pitanja.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {guest && (
            <>
              <button type="button" onClick={onSignUp} className="rounded-full bg-hype-yellow px-4 py-2 text-xs font-semibold text-chat-surface focus:outline-none focus:ring-2 focus:ring-hype-yellow focus:ring-offset-2 focus:ring-offset-chat-bg">
                Napravi nalog
              </button>
              <button type="button" onClick={onSignIn} className="rounded-full border border-chat-outline px-4 py-2 text-xs font-semibold text-chat-text focus:outline-none focus:ring-2 focus:ring-hype-yellow">
                Prijavi se
              </button>
            </>
          )}
          {quota.actions.includes('view_premium') && (
            <button type="button" onClick={onPremium} className="rounded-full bg-hype-yellow px-4 py-2 text-xs font-semibold text-chat-surface focus:outline-none focus:ring-2 focus:ring-hype-yellow focus:ring-offset-2 focus:ring-offset-chat-bg">
              Pogledaj Premium
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export const ConversationThread = ({
  messages,
  loading,
  error,
  quota,
  onRetry,
  onFollowUp,
  onSignIn,
  onSignUp,
  onPremium,
}: ConversationThreadProps) => (
  <div className="mx-auto w-full max-w-3xl space-y-7 px-4 py-8 sm:px-8 lg:max-w-[820px] lg:space-y-8 lg:px-6 lg:pb-10">
    {messages.map((message) =>
      message.role === 'user' ? (
        <div key={message.id} className="flex justify-end">
          <div className="max-w-[88%] rounded-2xl rounded-br-md bg-[var(--app-user-message)] px-4 py-3 text-[15px] leading-6 text-white sm:max-w-[75%]">
            {message.imagePreviews?.length ? <div className="mb-2 flex flex-wrap gap-2">{message.imagePreviews.map((url, index) => <img key={url} src={url} alt={`Priložena slika ${index + 1}`} className="max-h-40 max-w-40 rounded-lg object-contain" />)}</div> : null}
            {message.documentName ? (
              <div className="mb-2 flex max-w-full items-center gap-2 rounded-lg bg-black/15 px-3 py-2 text-xs">
                <FileText size={15} className="flex-none" />
                <span className="truncate">{message.documentName}</span>
                <span className="flex-none uppercase opacity-75">{message.documentType}</span>
              </div>
            ) : null}
            <p className="whitespace-pre-wrap break-words">{message.text}</p>
          </div>
        </div>
      ) : (
        <div key={message.id} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-hype-yellow text-xs font-black text-chat-surface">A</div>
          <AssistantResponse response={message.response} onFollowUp={onFollowUp} disabled={loading} />
        </div>
      ),
    )}

    {loading && (
      <div className="flex items-center gap-3 text-sm text-chat-muted" role="status">
        <Loader2 size={17} className="animate-spin" />
        AskHype radi na odgovoru...
      </div>
    )}

    {error && (
      <div className="flex items-center justify-between gap-4 border-l-2 border-red-300 py-2 pl-4">
        <p className="text-sm leading-6 text-chat-text">{error}</p>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex flex-none items-center gap-2 rounded-full border border-chat-outline px-3 py-2 text-xs font-semibold text-chat-text focus:outline-none focus:ring-2 focus:ring-hype-yellow"
        >
          <RefreshCcw size={13} />
          Ponovi
        </button>
      </div>
    )}

    <QuotaNotice quota={quota} onSignIn={onSignIn} onSignUp={onSignUp} onPremium={onPremium} />
  </div>
);
