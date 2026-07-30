import React, { useEffect, useMemo, useReducer, useRef } from 'react';
import { ExternalLink, Loader2, MapPin, RefreshCcw } from 'lucide-react';
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

const RecommendationResponseCard: React.FC<{ recommendation: ChatRecommendation }> = ({
  recommendation,
}) => {
  const imageUrl =
    isUsableImageUrl(recommendation.image_url) && recommendation.image_url
      ? recommendation.image_url
      : imageUtils.fallbackImage;

  return (
    <article className="bg-hype-white rounded-2xl overflow-hidden shadow-sm border border-hype-gray">
      <div className="relative bg-hype-gray" style={{ aspectRatio: '16/9' }}>
        <img
          src={imageUrl}
          alt={recommendation.title}
          onError={imageUtils.onImageError}
          className="h-full w-full object-cover"
          loading="lazy"
        />
        <span className="absolute left-2 top-2 rounded-full bg-hype-yellow px-3 py-1 text-xs font-bold text-navy-900">
          {recommendation.category}
        </span>
      </div>

      <div className="space-y-3 p-4">
        <div>
          <h3 className="text-base font-bold text-navy-900">{recommendation.title}</h3>
          <p className="mt-1 text-sm leading-5 text-navy-700">
            {recommendation.short_description}
          </p>
        </div>

        <div className="flex flex-wrap gap-2 text-xs text-navy-700">
          <span className="inline-flex items-center gap-1 rounded-full bg-hype-gray px-3 py-1">
            <MapPin size={12} />
            {recommendation.location}
          </span>
          {recommendation.estimated_price && (
            <span className="rounded-full bg-hype-gray px-3 py-1">
              {recommendation.estimated_price}
            </span>
          )}
          {recommendation.date_or_duration && (
            <span className="rounded-full bg-hype-gray px-3 py-1">
              {recommendation.date_or_duration}
            </span>
          )}
        </div>

        <div className="rounded-xl border-l-4 border-hype-yellow bg-hype-light p-3">
          <p className="text-xs font-bold text-navy-900">Zašto preporučujemo</p>
          <p className="mt-1 text-xs leading-5 text-navy-700">{recommendation.reason}</p>
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

const AssistantMessage: React.FC<{
  response: ChatResponse;
  onFollowUp: (text: string) => void;
  disabled: boolean;
}> = ({ response, onFollowUp, disabled }) => {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl rounded-bl-none bg-hype-gray px-4 py-3 text-navy-900">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm leading-6">{response.summary}</p>
          {import.meta.env.DEV && (
            <span className="rounded-full bg-hype-white px-2 py-1 text-[10px] font-semibold uppercase text-navy-600">
              {response.provider}
            </span>
          )}
        </div>
      </div>

      <div className="space-y-4">
        {response.recommendations.map((recommendation) => (
          <RecommendationResponseCard key={recommendation.id} recommendation={recommendation} />
        ))}
      </div>

      <SourcesList sources={response.sources} />

      {response.follow_up_actions.length > 0 && (
        <div className="rounded-2xl bg-hype-light p-4">
          <p className="mb-3 text-xs font-bold text-navy-900">Šta dalje?</p>
          <div className="flex flex-wrap gap-2">
            {response.follow_up_actions.map((action) => (
              <button
                key={action}
                type="button"
                disabled={disabled}
                onClick={() => onFollowUp(action)}
                className="rounded-full bg-hype-white px-3 py-2 text-left text-xs font-semibold text-navy-800 shadow-sm transition hover:bg-hype-yellow disabled:cursor-not-allowed disabled:opacity-60"
              >
                {action}
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
    <div className="pb-40 md:pb-6 overflow-x-hidden">
      <AppHeader title="Pitaj" />

      <main className="mx-auto max-w-md px-4 py-6">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-navy-900">Pitaj AskHype</h1>
          <p className="text-sm text-navy-600">
            Lokalni vodič za izlaske, hranu, događaje i putovanja po Balkanu.
          </p>
        </div>

        <div className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-4 scrollbar-hide">
          <FilterChip label={`📍 ${location}`} variant="active" />
          <FilterChip label="🇷🇸 Srpski" variant="active" />
          {(interests.length ? interests.slice(0, 2) : ['muzika', 'noćni život']).map((interest) => (
            <FilterChip key={interest} label={interest} />
          ))}
        </div>

        {state.messages.length === 0 ? (
          <section className="mb-6 space-y-5">
            <div className="rounded-2xl bg-hype-gray px-4 py-5">
              <p className="text-sm font-bold text-navy-900">Zdravo, ja sam AskHype.</p>
              <p className="mt-2 text-sm leading-6 text-navy-700">
                Pitaj me za večerašnji izlazak, vikend putovanje, restoran ili događaj. Odgovor
                stiže iz lokalnog mock backend-a kao strukturisana preporuka.
              </p>
            </div>

            <div>
              <p className="mb-3 text-xs font-bold text-navy-900">Probaj jedan prompt</p>
              <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2 scrollbar-hide">
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
          <div className="mb-6 space-y-5">
            {state.messages.map((message) => (
              <div
                key={message.id}
                className={message.role === 'user' ? 'flex justify-end' : 'block'}
              >
                {message.role === 'user' ? (
                  <div className="max-w-[82%] rounded-2xl rounded-br-none bg-navy-900 px-4 py-3 text-hype-white">
                    <p className="break-words text-sm leading-5">{message.text}</p>
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
            <div className="inline-flex items-center gap-2 rounded-2xl rounded-bl-none bg-hype-gray px-4 py-3 text-sm font-medium text-navy-700">
              <Loader2 size={16} className="animate-spin" />
              AskHype piše odgovor...
            </div>
          </div>
        )}

        {state.error && (
          <div className="mb-6 rounded-2xl border border-hype-yellow bg-hype-light p-4">
            <p className="text-sm leading-6 text-navy-800">{state.error}</p>
            <button
              type="button"
              onClick={handleRetry}
              disabled={state.isLoading}
              className="mt-3 inline-flex items-center gap-2 rounded-full bg-navy-900 px-4 py-2 text-sm font-semibold text-hype-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCcw size={14} />
              Pokušaj ponovo
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      <div className="fixed bottom-20 left-0 right-0 z-20 border-t border-hype-gray bg-hype-white md:relative md:bottom-auto md:border-t-0 md:mt-6">
        <div className="mx-auto max-w-md px-4 py-4">
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
