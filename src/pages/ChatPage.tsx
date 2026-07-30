import React, { useEffect, useMemo, useReducer, useRef } from 'react';
import {
  CalendarDays,
  CircleDollarSign,
  ExternalLink,
  Info,
  Loader2,
  MapPin,
  RefreshCcw,
  Sparkles,
} from 'lucide-react';
import { AppHeader, AskHypeInput, FilterChip, QuickPromptChip } from '../components';
import { sendChatMessage } from '../services/chat-api';
import type { ChatResponse, ChatRecommendation, SourceReference } from '../types/chat';
import { dateUtils, imageUtils, storageUtils, validationUtils } from '../utils';

type ChatMessage =
  | {
      id: string;
      role: 'user';
      text: string;
      createdAt: string;
    }
  | {
      id: string;
      role: 'assistant';
      response: ChatResponse;
      createdAt: string;
    };

interface ChatState {
  messages: ChatMessage[];
  conversationId: string | null;
  isLoading: boolean;
  error: string | null;
  lastSubmittedText: string | null;
}

type ChatAction =
  | { type: 'submit'; message: ChatMessage; text: string }
  | { type: 'success'; message: ChatMessage; conversationId: string }
  | { type: 'failure'; error: string }
  | { type: 'clear_error' };

const initialState: ChatState = {
  messages: [],
  conversationId: null,
  isLoading: false,
  error: null,
  lastSubmittedText: null,
};

const examplePrompts = [
  { id: 'nightlife', text: 'Gde mogu da izađem ovog vikenda u Beogradu?', iconName: 'Music' },
  { id: 'travel', text: 'Isplaniraj mi vikend putovanje u Crnu Goru.', iconName: 'Map' },
  { id: 'food', text: 'Gde mogu dobro da večeram u Beogradu?', iconName: 'Utensils' },
];

const chatReducer = (state: ChatState, action: ChatAction): ChatState => {
  switch (action.type) {
    case 'submit':
      return {
        ...state,
        messages: [...state.messages, action.message],
        isLoading: true,
        error: null,
        lastSubmittedText: action.text,
      };
    case 'success':
      return {
        ...state,
        messages: [...state.messages, action.message],
        conversationId: action.conversationId,
        isLoading: false,
        error: null,
      };
    case 'failure':
      return {
        ...state,
        isLoading: false,
        error: action.error,
      };
    case 'clear_error':
      return {
        ...state,
        error: null,
      };
    default:
      return state;
  }
};

const createMessageId = (prefix: string) =>
  `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;

const formatSourceDate = (value?: string | null) => {
  if (!value) return null;
  return dateUtils.formatDate(value);
};

const isUsableImageUrl = (value?: string | null) => {
  return Boolean(value && validationUtils.isValidUrl(value));
};

const formatFollowUpLabel = (value: string) => {
  const normalized = value.trim().replace(/\s+/g, ' ');
  if (normalized.length <= 42) return normalized;

  const sentence = normalized.split(/[.?!]/)[0]?.trim();
  const candidate = sentence && sentence.length >= 12 ? sentence : normalized;

  return `${candidate.slice(0, 39).trim()}...`;
};

const RecommendationResponseCard: React.FC<{ recommendation: ChatRecommendation }> = ({
  recommendation,
}) => {
  const imageUrl = isUsableImageUrl(recommendation.image_url)
    ? recommendation.image_url
    : null;

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-hype-white shadow-sm">
      {imageUrl ? (
        <div className="relative bg-hype-gray" style={{ aspectRatio: '16/9' }}>
          <img
            src={imageUrl}
            alt={recommendation.title}
            onError={imageUtils.onImageError}
            className="h-full w-full object-cover"
            loading="lazy"
          />
          <span className="absolute left-3 top-3 rounded-full bg-hype-yellow px-3 py-1 text-xs font-bold text-navy-900 shadow-sm">
            {recommendation.category}
          </span>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 bg-hype-light px-4 py-3">
          <span className="rounded-full bg-hype-yellow px-3 py-1 text-xs font-bold text-navy-900">
            {recommendation.category}
          </span>
          <span
            aria-hidden="true"
            className="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-navy-900 text-hype-yellow"
          >
            <Sparkles size={17} />
          </span>
        </div>
      )}

      <div className="space-y-3.5 p-4 sm:p-5">
        {imageUrl ? null : (
          <span className="sr-only">
          {recommendation.category}
          </span>
        )}

        <div>
          <h3 className="text-lg font-bold leading-6 text-navy-900 sm:text-xl">
            {recommendation.title}
          </h3>
          <p className="mt-1.5 text-sm leading-6 text-navy-700 sm:text-[15px]">
            {recommendation.short_description}
          </p>
        </div>

        <div className="grid gap-2 text-xs leading-5 text-navy-700 sm:grid-cols-3">
          <span className="inline-flex min-w-0 items-start gap-1.5 rounded-xl bg-hype-gray px-3 py-2">
            <MapPin size={14} className="mt-0.5 flex-shrink-0 text-navy-600" />
            <span className="min-w-0 break-words">{recommendation.location}</span>
          </span>
          {recommendation.estimated_price && (
            <span className="inline-flex min-w-0 items-start gap-1.5 rounded-xl bg-hype-gray px-3 py-2">
              <CircleDollarSign size={14} className="mt-0.5 flex-shrink-0 text-navy-600" />
              <span className="min-w-0 break-words">{recommendation.estimated_price}</span>
            </span>
          )}
          {recommendation.date_or_duration && (
            <span className="inline-flex min-w-0 items-start gap-1.5 rounded-xl bg-hype-gray px-3 py-2">
              <CalendarDays size={14} className="mt-0.5 flex-shrink-0 text-navy-600" />
              <span className="min-w-0 break-words">{recommendation.date_or_duration}</span>
            </span>
          )}
        </div>

        <div className="rounded-xl border-l-4 border-hype-yellow bg-yellow-50 p-3.5">
          <p className="text-xs font-bold uppercase tracking-wide text-navy-900">
            Zašto preporučujemo
          </p>
          <p className="mt-1.5 text-sm leading-6 text-navy-700">{recommendation.reason}</p>
        </div>

        {recommendation.source_url && (
          <a
            href={recommendation.source_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex max-w-full items-center gap-1 text-xs font-semibold text-navy-900 underline decoration-hype-yellow decoration-2 underline-offset-4"
          >
            <span className="truncate">Izvor preporuke</span>
            <ExternalLink size={12} className="flex-shrink-0" />
          </a>
        )}
      </div>
    </article>
  );
};

const SourcesList: React.FC<{ sources: SourceReference[] }> = ({ sources }) => {
  if (!sources.length) return null;

  return (
    <div className="rounded-2xl bg-hype-gray p-4">
      <p className="mb-3 text-xs font-bold text-navy-900">Izvori</p>
      <div className="space-y-2">
        {sources.map((source) => {
          const content = (
            <>
              <span className="break-words">{source.title}</span>
              {source.url && <ExternalLink size={12} className="mt-0.5 flex-shrink-0" />}
            </>
          );

          return (
            <div key={`${source.title}-${source.url ?? 'local'}`} className="text-xs text-navy-700">
              {source.url ? (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex max-w-full items-start gap-1 font-semibold text-navy-900"
                >
                  {content}
                </a>
              ) : (
                <p className="font-semibold text-navy-900">{source.title}</p>
              )}
              {source.last_verified && (
                <p className="mt-0.5 text-navy-600">
                  Poslednja provera: {formatSourceDate(source.last_verified)}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const UnverifiedNotice: React.FC = () => (
  <div className="flex items-start gap-2 rounded-2xl border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm leading-6 text-navy-700">
    <Info size={16} className="mt-1 flex-shrink-0 text-navy-700" />
    <p>Preporuke nisu proverene uživo. Proveri termine, cene i dostupnost pre posete.</p>
  </div>
);

const AssistantMessage: React.FC<{
  response: ChatResponse;
  onFollowUp: (text: string) => void;
  disabled: boolean;
}> = ({ response, onFollowUp, disabled }) => {
  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="rounded-2xl rounded-bl-md bg-hype-white px-4 py-3.5 text-navy-900 shadow-sm ring-1 ring-slate-200 sm:px-5 sm:py-4">
        <div className="flex items-start justify-between gap-3">
          <p className="min-w-0 text-[15px] leading-7 sm:text-base">{response.summary}</p>
          {import.meta.env.DEV && (
            <span className="mt-0.5 flex-shrink-0 rounded-full bg-hype-gray px-2 py-1 text-[10px] font-semibold uppercase text-navy-500">
              {response.provider}
            </span>
          )}
        </div>
      </div>

      <div className="space-y-3.5 sm:space-y-4">
        {response.recommendations.map((recommendation) => (
          <RecommendationResponseCard key={recommendation.id} recommendation={recommendation} />
        ))}
      </div>

      {response.sources.length > 0 ? <SourcesList sources={response.sources} /> : <UnverifiedNotice />}

      {response.follow_up_actions.length > 0 && (
        <div className="rounded-2xl bg-hype-light p-4 sm:p-5">
          <p className="mb-3 text-xs font-bold text-navy-900">Šta dalje?</p>
          <div className="flex flex-wrap gap-2">
            {response.follow_up_actions.map((action) => (
              <button
                key={action}
                type="button"
                disabled={disabled}
                onClick={() => onFollowUp(action)}
                title={action}
                aria-label={action}
                className="max-w-full rounded-full bg-hype-white px-3.5 py-2 text-left text-xs font-semibold leading-5 text-navy-800 shadow-sm ring-1 ring-slate-200 transition hover:bg-hype-yellow focus:outline-none focus:ring-2 focus:ring-navy-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm"
              >
                <span className="block max-w-[17rem] whitespace-normal break-words sm:max-w-md">
                  {formatFollowUpLabel(action)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export const ChatPage: React.FC = () => {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const userPreferences = useMemo(() => storageUtils.getUserPreferences(), []);
  const location = userPreferences.city || 'Beograd';
  const interests = userPreferences.interests ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [state.messages.length, state.isLoading, state.error]);

  const submitMessage = async (rawValue: string) => {
    const text = rawValue.trim();

    if (!text || state.isLoading) {
      return;
    }

    const userMessage: ChatMessage = {
      id: createMessageId('user'),
      role: 'user',
      text,
      createdAt: new Date().toISOString(),
    };

    dispatch({ type: 'submit', message: userMessage, text });

    try {
      const response = await sendChatMessage({
        message: text,
        conversation_id: state.conversationId,
        location,
        language: userPreferences.language || 'sr',
        interests,
      });

      dispatch({
        type: 'success',
        conversationId: response.conversation_id,
        message: {
          id: createMessageId('assistant'),
          role: 'assistant',
          response,
          createdAt: new Date().toISOString(),
        },
      });
    } catch {
      dispatch({
        type: 'failure',
        error:
          'AskHype trenutno ne može da odgovori. Proveri da li je backend pokrenut i pokušaj ponovo.',
      });
    }
  };

  const handleRetry = () => {
    const retryText = state.lastSubmittedText;
    dispatch({ type: 'clear_error' });

    if (retryText) {
      void submitMessage(retryText);
    }
  };

  return (
    <div className="overflow-x-hidden pb-40 md:pb-6">
      <AppHeader title="Pitaj" />

      <main className="mx-auto w-full max-w-[760px] px-4 py-6 sm:px-5 md:px-6 md:py-8">
        <div className="mb-6 sm:mb-7">
          <h1 className="text-3xl font-bold leading-tight text-navy-900 sm:text-4xl">
            Pitaj AskHype
          </h1>
          <p className="mt-1.5 text-sm leading-6 text-navy-600 sm:text-base">
            Lokalni vodič za izlaske, hranu, događaje i putovanja po Balkanu.
          </p>
        </div>

        <div className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-4 scrollbar-hide sm:-mx-5 sm:px-5 md:-mx-6 md:px-6">
          <FilterChip label={`📍 ${location}`} variant="active" />
          <FilterChip label="🇷🇸 Srpski" variant="active" />
          {(interests.length ? interests.slice(0, 2) : ['muzika', 'noćni život']).map((interest) => (
            <FilterChip key={interest} label={interest} />
          ))}
        </div>

        {state.messages.length === 0 ? (
          <section className="mb-6 space-y-5 sm:space-y-6">
            <div className="rounded-2xl bg-hype-white px-4 py-5 shadow-sm ring-1 ring-slate-200 sm:px-5">
              <p className="text-base font-bold text-navy-900">Zdravo, ja sam AskHype.</p>
              <p className="mt-2 text-sm leading-6 text-navy-700 sm:text-[15px]">
                Pitaj me za večerašnji izlazak, vikend putovanje, restoran ili događaj. Odgovor
                stiže kao strukturisana preporuka spremna za brzo planiranje.
              </p>
            </div>

            <div>
              <p className="mb-3 text-xs font-bold text-navy-900">Probaj jedan prompt</p>
              <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2 scrollbar-hide sm:-mx-5 sm:px-5 md:-mx-6 md:px-6">
                {examplePrompts.map((prompt) => (
                  <QuickPromptChip
                    key={prompt.id}
                    text={prompt.text}
                    iconName={prompt.iconName}
                    onClick={() => void submitMessage(prompt.text)}
                    variant="default"
                  />
                ))}
              </div>
            </div>
          </section>
        ) : (
          <div className="mb-6 space-y-6">
            {state.messages.map((message) => (
              <div
                key={message.id}
                className={message.role === 'user' ? 'flex justify-end' : 'block'}
              >
                {message.role === 'user' ? (
                  <div className="max-w-[88%] rounded-2xl rounded-br-md bg-navy-900 px-4 py-3 text-hype-white shadow-sm sm:max-w-[78%]">
                    <p className="break-words text-sm leading-6 sm:text-[15px]">{message.text}</p>
                  </div>
                ) : (
                  <AssistantMessage
                    response={message.response}
                    onFollowUp={(text) => void submitMessage(text)}
                    disabled={state.isLoading}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        {state.isLoading && (
          <div className="mb-6 flex justify-start">
            <div className="inline-flex items-center gap-2 rounded-2xl rounded-bl-md bg-hype-white px-4 py-3 text-sm font-medium text-navy-700 shadow-sm ring-1 ring-slate-200">
              <Loader2 size={16} className="animate-spin" />
              AskHype piše odgovor...
            </div>
          </div>
        )}

        {state.error && (
          <div className="mb-6 rounded-2xl border border-hype-yellow bg-hype-white p-4 shadow-sm">
            <p className="text-sm leading-6 text-navy-800">{state.error}</p>
            <button
              type="button"
              onClick={handleRetry}
              disabled={state.isLoading}
              className="mt-3 inline-flex items-center gap-2 rounded-full bg-navy-900 px-4 py-2 text-sm font-semibold text-hype-white transition hover:bg-navy-800 focus:outline-none focus:ring-2 focus:ring-navy-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCcw size={14} />
              Pokušaj ponovo
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      <div className="fixed bottom-20 left-0 right-0 z-20 border-t border-hype-gray bg-hype-white/95 backdrop-blur md:relative md:bottom-auto md:mt-6 md:border-t-0 md:bg-transparent md:backdrop-blur-0">
        <div className="mx-auto w-full max-w-[760px] px-4 py-3 sm:px-5 md:px-6 md:py-4">
          <AskHypeInput
            placeholder="Postavi pitanje AskHype-u..."
            onSubmit={submitMessage}
            disabled={state.isLoading}
          />
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
