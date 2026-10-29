import { ExternalLink, Loader2, LockKeyhole, MapPin, RefreshCcw } from 'lucide-react';
import type { QuotaLimitPayload } from '../../services/chat-api';
import type { ChatResponse } from '../../types/chat';
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

const AssistantResponse = ({
  response,
  onFollowUp,
  disabled,
}: {
  response: ChatResponse;
  onFollowUp: (prompt: string) => void;
  disabled: boolean;
}) => (
  <div className="space-y-5 lg:space-y-6">
    <p className="whitespace-pre-wrap text-[15px] leading-7 text-chat-text">{response.summary}</p>

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

    {response.sources.length > 0 && (
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
          <div className="max-w-[88%] rounded-2xl rounded-br-md bg-chat-hover px-4 py-3 text-[15px] leading-6 text-white sm:max-w-[75%]">
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
        AskHype razmišlja...
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
