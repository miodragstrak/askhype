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
    <p className="whitespace-pre-wrap text-[15px] leading-7 text-slate-800">{response.summary}</p>

    {response.recommendations.length > 0 && (
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-1 lg:grid-cols-2 lg:gap-4">
        {response.recommendations.map((recommendation) => (
          <article key={recommendation.id} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-amber-700">{recommendation.category}</p>
                <h3 className="mt-1 text-base font-semibold leading-6 text-slate-950">
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
                  className="inline-flex h-9 w-9 flex-none items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-slate-950"
                >
                  <ExternalLink size={16} />
                </a>
              )}
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-600">{recommendation.short_description}</p>
            <div className="mt-3 flex items-start gap-2 text-xs text-slate-500">
              <MapPin size={14} className="mt-0.5 flex-none" />
              <span>{recommendation.location}</span>
            </div>
            {(recommendation.estimated_price || recommendation.date_or_duration) && (
              <p className="mt-2 text-xs font-medium text-slate-600">
                {[recommendation.estimated_price, recommendation.date_or_duration].filter(Boolean).join(' · ')}
              </p>
            )}
            <p className="mt-3 border-t border-slate-100 pt-3 text-sm leading-6 text-slate-700">
              {recommendation.reason}
            </p>
          </article>
        ))}
      </div>
    )}

    {response.sources.length > 0 && (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
        <span className="font-semibold text-slate-700">Izvori</span>
        {response.sources.map((source) =>
          source.url ? (
            <a
              key={`${source.title}-${source.url}`}
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex max-w-full flex-wrap items-center gap-1 underline decoration-slate-300 underline-offset-4 hover:text-slate-950"
            >
              {source.title}
              <ExternalLink size={11} />
              {hypeSourceOwner(source.url) ? (
                <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-blue-800 no-underline">
                  {hypeSourceOwner(source.url)}
                </span>
              ) : response.answer_type === 'hype_content' ? (
                <span className="text-[10px] text-slate-500">Spoljni izvor</span>
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
            className="min-h-9 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-left text-xs font-medium text-slate-700 transition hover:border-slate-400 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-slate-950 disabled:opacity-50"
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
    <div className="flex gap-3 border-l-2 border-yellow-400 py-2 pl-4">
      <LockKeyhole size={18} className="mt-1 flex-none text-slate-700" />
      <div>
        <p className="text-sm font-semibold text-slate-950">Dostigao si limit pitanja.</p>
        <p className="mt-1 text-sm leading-6 text-slate-600">
          Iskorišćeno je {quota.used} od {quota.limit} pitanja.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {guest && (
            <>
              <button type="button" onClick={onSignUp} className="rounded-full bg-slate-950 px-4 py-2 text-xs font-semibold text-white">
                Napravi nalog
              </button>
              <button type="button" onClick={onSignIn} className="rounded-full border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-800">
                Prijavi se
              </button>
            </>
          )}
          {quota.actions.includes('view_premium') && (
            <button type="button" onClick={onPremium} className="rounded-full bg-yellow-300 px-4 py-2 text-xs font-semibold text-slate-950">
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
          <div className="max-w-[88%] rounded-2xl rounded-br-md bg-slate-900 px-4 py-3 text-[15px] leading-6 text-white sm:max-w-[75%]">
            <p className="whitespace-pre-wrap break-words">{message.text}</p>
          </div>
        </div>
      ) : (
        <div key={message.id} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-yellow-300 text-xs font-black text-slate-950">A</div>
          <AssistantResponse response={message.response} onFollowUp={onFollowUp} disabled={loading} />
        </div>
      ),
    )}

    {loading && (
      <div className="flex items-center gap-3 text-sm text-slate-500" role="status">
        <Loader2 size={17} className="animate-spin" />
        AskHype razmišlja...
      </div>
    )}

    {error && (
      <div className="flex items-center justify-between gap-4 border-l-2 border-red-300 py-2 pl-4">
        <p className="text-sm leading-6 text-slate-700">{error}</p>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex flex-none items-center gap-2 rounded-full border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-950"
        >
          <RefreshCcw size={13} />
          Ponovi
        </button>
      </div>
    )}

    <QuotaNotice quota={quota} onSignIn={onSignIn} onSignUp={onSignUp} onPremium={onPremium} />
  </div>
);
