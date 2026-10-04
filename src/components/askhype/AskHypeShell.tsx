import { useEffect, useMemo, useRef, useState } from 'react';
import { History, Plus, UserRound } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth';
import { PromptLimitError, sendChatMessage, type QuotaLimitPayload } from '../../services/chat-api';
import type { LocalConversation, LocalMessage } from '../../types/conversation';
import { useUsage } from '../../usage';
import { storageUtils } from '../../utils';
import { AskHypeLogo } from '../branding/AskHypeLogo';
import {
  conversationTitle,
  loadConversations,
  saveConversations,
  sortConversations,
} from '../../utils/conversation-storage';
import { ConversationSidebar } from './ConversationSidebar';
import { ConversationThread } from './ConversationThread';
import { EmptyConversation } from './EmptyConversation';
import { PromptComposer } from './PromptComposer';

const createId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

export const AskHypeShell = () => {
  const navigate = useNavigate();
  const { session, user, profile } = useAuth();
  const { usage, applyUsageSnapshot, refreshUsage } = useUsage();
  const [conversations, setConversations] = useState<LocalConversation[]>(loadConversations);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaLimitPayload | null>(null);
  const [lastSubmission, setLastSubmission] = useState<{ conversationId: string; text: string } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const preferences = useMemo(() => storageUtils.getUserPreferences(), []);
  const activeConversation = conversations.find((conversation) => conversation.id === activeId) ?? null;

  useEffect(() => {
    saveConversations(conversations);
  }, [conversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [activeConversation?.messages.length, loading, error, quota]);

  const upsertConversation = (conversation: LocalConversation) => {
    setConversations((current) =>
      sortConversations([conversation, ...current.filter((item) => item.id !== conversation.id)]),
    );
  };

  const submitPrompt = async (
    rawPrompt: string,
    options: { appendUser?: boolean; conversationId?: string } = {},
  ) => {
    const prompt = rawPrompt.trim();
    if (!prompt || loading) return;

    const now = new Date().toISOString();
    const existing = conversations.find(
      (conversation) => conversation.id === (options.conversationId ?? activeId),
    );
    const conversation: LocalConversation = existing ?? {
      id: createId(),
      title: conversationTitle(prompt),
      createdAt: now,
      updatedAt: now,
      serverConversationId: null,
      messages: [],
    };
    const appendUser = options.appendUser ?? true;
    const userMessage: LocalMessage = {
      id: createId(),
      role: 'user',
      text: prompt,
      createdAt: now,
    };
    const pendingConversation = {
      ...conversation,
      updatedAt: now,
      messages: appendUser ? [...conversation.messages, userMessage] : conversation.messages,
    };

    setActiveId(conversation.id);
    upsertConversation(pendingConversation);
    setLastSubmission({ conversationId: conversation.id, text: prompt });
    setLoading(true);
    setError(null);
    setQuota(null);

    try {
      const result = await sendChatMessage(
        {
          message: prompt,
          conversation_id: conversation.serverConversationId,
          location: preferences.city || 'Beograd',
          language: preferences.language || 'sr',
          interests: preferences.interests ?? [],
        },
        { accessToken: session?.access_token },
      );
      const assistantMessage: LocalMessage = {
        id: createId(),
        role: 'assistant',
        response: result.data,
        createdAt: new Date().toISOString(),
      };

      setConversations((current) => {
        const latest = current.find((item) => item.id === conversation.id) ?? pendingConversation;
        const updated = {
          ...latest,
          updatedAt: assistantMessage.createdAt,
          serverConversationId: result.data.conversation_id,
          messages: [...latest.messages, assistantMessage],
        };
        return sortConversations([updated, ...current.filter((item) => item.id !== updated.id)]);
      });
      applyUsageSnapshot(result.usage);
      void refreshUsage();
    } catch (requestError) {
      if (requestError instanceof PromptLimitError) {
        setQuota(requestError.payload);
        applyUsageSnapshot(requestError.payload);
      } else {
        setError('AskHype trenutno ne može da odgovori. Pokušaj ponovo.');
      }
    } finally {
      setLoading(false);
    }
  };

  const startNew = () => {
    setActiveId(null);
    setError(null);
    setQuota(null);
    setSidebarOpen(false);
  };

  const selectConversation = (id: string) => {
    setActiveId(id);
    setError(null);
    setQuota(null);
    setSidebarOpen(false);
  };

  const deleteConversation = (id: string) => {
    setConversations((current) => current.filter((conversation) => conversation.id !== id));
    if (activeId === id) startNew();
  };

  const authNavigate = (mode: 'signIn' | 'signUp') => {
    navigate('/auth', { state: { redirectTo: '/', mode } });
  };

  const accountLabel = profile?.display_name || user?.email || 'Nalog';

  return (
    <div className="flex h-dvh min-h-[560px] flex-col overflow-hidden bg-white text-slate-950">
      <header className="flex h-16 flex-none items-center justify-between border-b border-slate-200 bg-white px-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="Otvori istoriju razgovora"
            title="Istorija"
            className="inline-flex h-10 w-10 items-center justify-center rounded-md text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-950 md:hidden"
          >
            <History size={19} />
          </button>
          <AskHypeLogo
            variant="conversation"
            className="min-h-11 rounded-md px-1 py-1 focus:outline-none focus:ring-2 focus:ring-slate-950"
          />
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          {usage && (
            <span className="hidden text-xs text-slate-500 sm:inline">
              {usage.remaining} pitanja
            </span>
          )}
          <button
            type="button"
            onClick={startNew}
            aria-label="Novi razgovor"
            title="Novi razgovor"
            className="inline-flex h-10 w-10 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-950 md:hidden"
          >
            <Plus size={19} />
          </button>
          <button
            type="button"
            onClick={() => navigate(user ? '/profile' : '/auth')}
            aria-label={user ? `Otvori profil: ${accountLabel}` : 'Prijavi se'}
            title={user ? accountLabel : 'Prijavi se'}
            className="inline-flex h-10 items-center gap-2 rounded-full px-2 text-sm font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-950 sm:px-3"
          >
            <UserRound size={18} />
            <span className="hidden max-w-36 truncate sm:block">{user ? accountLabel : 'Prijavi se'}</span>
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <ConversationSidebar
          conversations={conversations}
          activeId={activeId}
          mobileOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNew={startNew}
          onSelect={selectConversation}
          onDelete={deleteConversation}
        />

        <main className="flex min-w-0 flex-1 flex-col bg-white">
          <div className="min-h-0 flex-1 overflow-y-auto">
            {activeConversation?.messages.length ? (
              <ConversationThread
                messages={activeConversation.messages}
                loading={loading}
                error={error}
                quota={quota}
                onRetry={() => {
                  if (lastSubmission) {
                    void submitPrompt(lastSubmission.text, {
                      appendUser: false,
                      conversationId: lastSubmission.conversationId,
                    });
                  }
                }}
                onFollowUp={(prompt) => void submitPrompt(prompt)}
                onSignIn={() => authNavigate('signIn')}
                onSignUp={() => authNavigate('signUp')}
                onPremium={() => navigate('/premium')}
              />
            ) : (
              <EmptyConversation onSelect={(prompt) => void submitPrompt(prompt)} />
            )}
            <div ref={bottomRef} />
          </div>

          <div className="flex-none border-t border-slate-100 bg-white px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-6 sm:pb-4">
            <div className="mx-auto max-w-3xl">
              <PromptComposer onSubmit={(prompt) => void submitPrompt(prompt)} disabled={loading || Boolean(quota)} />
              <p className="mt-2 text-center text-[11px] text-slate-400">
                Proveri termine, cene i dostupnost pre odluke.
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
