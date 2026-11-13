import { useEffect, useMemo, useRef, useState } from 'react';
import { History, Plus, UserRound } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth';
import { PromptLimitError, runResearch, sendChatMessage, sendDocumentAnalysis, sendPresentationGeneration, sendXlsxTransformation, type QuotaLimitPayload } from '../../services/chat-api';
import type { LocalConversation, LocalMessage } from '../../types/conversation';
import type { ChatResponse, DocumentAction, PendingDocument, PendingImage } from '../../types/chat';
import { useUsage } from '../../usage';
import { storageUtils } from '../../utils';
import { AskHypeLogo } from '../branding/AskHypeLogo';
import { ThemeToggle } from '../ThemeToggle';
import {
  conversationTitle,
  loadActiveConversationId,
  loadConversations,
  saveActiveConversationId,
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
  const [activeId, setActiveId] = useState<string | null>(() => loadActiveConversationId(conversations));
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaLimitPayload | null>(null);
  const [lastSubmission, setLastSubmission] = useState<{ conversationId: string; text: string; images: PendingImage[]; document: PendingDocument | null; documentAction: DocumentAction } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const preferences = useMemo(() => storageUtils.getUserPreferences(), []);
  const activeConversation = conversations.find((conversation) => conversation.id === activeId) ?? null;

  useEffect(() => {
    saveConversations(conversations);
  }, [conversations]);

  useEffect(() => {
    saveActiveConversationId(activeId);
  }, [activeId]);

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
    images: PendingImage[] = [],
    document: PendingDocument | null = null,
    documentAction: DocumentAction = 'analyze',
    options: { appendUser?: boolean; conversationId?: string } = {},
  ): Promise<boolean> => {
    const visiblePrompt = rawPrompt.trim();
    const prompt = visiblePrompt || (images.length ? 'Analiziraj priloženu sliku/slike i opiši relevantne informacije.' : '');
    if (!prompt || loading || (document && images.length > 0)) return false;

    const now = new Date().toISOString();
    const existing = conversations.find(
      (conversation) => conversation.id === (options.conversationId ?? activeId),
    );
    const conversation: LocalConversation = existing ?? {
      id: createId(),
      title: conversationTitle(visiblePrompt || (document ? document.file.name : 'Analiza slike')),
      createdAt: now,
      updatedAt: now,
      serverConversationId: null,
      messages: [],
    };
    const appendUser = options.appendUser ?? true;
    const lastMessage = conversation.messages.at(-1);
    const priorMessages =
      !appendUser && lastMessage?.role === 'user'
        ? conversation.messages.slice(0, -1)
        : conversation.messages;
    const history = priorMessages.slice(-6).map((message) => ({
      role: message.role,
      text: message.role === 'user' ? message.text : message.response.summary,
    }));
    const userMessage: LocalMessage = {
      id: createId(),
      role: 'user',
      text: visiblePrompt || 'Priložena slika',
      imagePreviews: images.map((image) => image.previewUrl),
      documentName: document?.file.name,
      documentType: document?.file.name.split('.').pop()?.toLocaleUpperCase(),
      documentAction: document ? documentAction : undefined,
      createdAt: now,
    };
    const pendingConversation = {
      ...conversation,
      updatedAt: now,
      messages: appendUser ? [...conversation.messages, userMessage] : conversation.messages,
    };

    setActiveId(conversation.id);
    upsertConversation(pendingConversation);
    setLastSubmission({ conversationId: conversation.id, text: prompt, images, document, documentAction });
    setLoading(true);
    setError(null);
    setQuota(null);

    try {
      let result;
      if (documentAction === 'research') {
        const job = await runResearch(prompt, document?.file ?? null, { accessToken: session?.access_token });
        if (!job.result) throw new Error('Deep Research nije vratio rezultat.');
        const data: ChatResponse = {
          conversation_id: conversation.serverConversationId || `research_${job.research_id}`,
          provider: job.result.provider, answer_type: 'deep_research', summary: job.result.summary,
          recommendations: [], follow_up_actions: [],
          sources: job.result.sources.map((source) => ({ title: source.title, url: source.url })),
          generated_at: job.result.generated_at, research: job.result,
        };
        result = { data, usage: null };
      } else if (documentAction === 'presentation') {
        const presentation = await sendPresentationGeneration(
          prompt, document?.file ?? null, { accessToken: session?.access_token },
        );
        const warningText = presentation.warnings.length
          ? `\n\nNapomene:\n${presentation.warnings.map((warning) => `• ${warning}`).join('\n')}`
          : '';
        const data: ChatResponse = {
          conversation_id: conversation.serverConversationId || `pptx_${createId()}`,
          provider: 'document', answer_type: 'presentation_generation',
          summary: presentation.summary + warningText,
          recommendations: [], follow_up_actions: [],
          sources: [],
          generated_at: new Date().toISOString(),
          presentation_slide_count: presentation.slideCount,
          download: { filename: presentation.filename, url: URL.createObjectURL(presentation.blob), available: true },
        };
        result = { data, usage: presentation.usage };
      } else if (document) {
        if (documentAction === 'transform') {
          const transformed = await sendXlsxTransformation(
            document.file, prompt, { accessToken: session?.access_token },
          );
          const warningText = transformed.warnings.length
            ? `\n\nNapomene:\n${transformed.warnings.map((warning) => `• ${warning}`).join('\n')}`
            : '';
          const data: ChatResponse = {
            conversation_id: conversation.serverConversationId || `xlsx_${createId()}`,
            provider: 'document', answer_type: 'xlsx_transformation',
            summary: transformed.summary + warningText,
            recommendations: [], follow_up_actions: [], sources: [{ title: document.file.name }],
            generated_at: new Date().toISOString(),
            download: { filename: transformed.filename, url: URL.createObjectURL(transformed.blob), available: true },
          };
          result = { data, usage: transformed.usage };
        } else {
        const documentResult = await sendDocumentAnalysis(
          document.file,
          prompt,
          { accessToken: session?.access_token },
        );
        const warningText = documentResult.data.warnings.length
          ? `\n\nNapomene:\n${documentResult.data.warnings.map((warning) => `• ${warning}`).join('\n')}`
          : '';
        const data: ChatResponse = {
          conversation_id: conversation.serverConversationId || `doc_${createId()}`,
          provider: 'document',
          answer_type: 'document_analysis',
          summary: documentResult.data.answer + warningText,
          recommendations: [],
          follow_up_actions: [],
          sources: [{ title: documentResult.data.filename }],
          generated_at: documentResult.data.generated_at,
        };
        result = { data, usage: documentResult.usage };
        }
      } else {
        result = await sendChatMessage(
          {
            message: prompt,
            conversation_id: conversation.serverConversationId,
            location: preferences.city || 'Beograd',
            language: preferences.language || 'sr',
            interests: preferences.interests ?? [],
            history,
          },
          { accessToken: session?.access_token },
          images,
        );
      }
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
      return true;
    } catch (requestError) {
      if (requestError instanceof PromptLimitError) {
        setQuota(requestError.payload);
        applyUsageSnapshot(requestError.payload);
      } else {
        setError(requestError instanceof Error ? requestError.message : 'AskHype trenutno ne može da odgovori. Pokušaj ponovo.');
      }
      return false;
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
    <div className="askhype-conversation flex h-dvh min-h-[560px] flex-col overflow-hidden bg-chat-bg text-chat-text">
      <header className="flex h-16 flex-none items-center justify-between border-b border-chat-border bg-chat-surface px-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="Otvori istoriju razgovora"
            title="Istorija"
            className="inline-flex h-10 w-10 items-center justify-center rounded-md text-chat-text hover:bg-chat-hover focus:outline-none focus:ring-2 focus:ring-hype-yellow md:hidden"
          >
            <History size={19} />
          </button>
          <AskHypeLogo
            variant="conversation"
            className="focus:outline-none focus:ring-2 focus:ring-hype-yellow"
          />
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          {usage && (
            <span className="hidden text-xs text-chat-muted sm:inline">
              {usage.remaining} pitanja
            </span>
          )}
          <ThemeToggle conversation />
          <button
            type="button"
            onClick={startNew}
            aria-label="Novi razgovor"
            title="Novi razgovor"
            className="inline-flex h-10 w-10 items-center justify-center rounded-md text-chat-muted hover:bg-chat-hover focus:outline-none focus:ring-2 focus:ring-hype-yellow md:hidden"
          >
            <Plus size={19} />
          </button>
          <button
            type="button"
            onClick={() => navigate(user ? '/profile' : '/auth')}
            aria-label={user ? `Otvori profil: ${accountLabel}` : 'Prijavi se'}
            title={user ? accountLabel : 'Prijavi se'}
            className="inline-flex h-10 items-center gap-2 rounded-full px-2 text-sm font-medium text-chat-text hover:bg-chat-hover focus:outline-none focus:ring-2 focus:ring-hype-yellow sm:px-3"
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

        <main className="flex min-w-0 flex-1 flex-col bg-chat-bg">
          <div className="min-h-0 flex-1 overflow-y-auto">
            {activeConversation?.messages.length ? (
              <ConversationThread
                messages={activeConversation.messages}
                loading={loading}
                error={error}
                quota={quota}
                onRetry={() => {
                  if (lastSubmission) {
                    void submitPrompt(lastSubmission.text, lastSubmission.images, lastSubmission.document, lastSubmission.documentAction, {
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
              <EmptyConversation />
            )}
            <div ref={bottomRef} />
          </div>

          <div className="flex-none border-t border-chat-border bg-chat-bg px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-6 sm:pb-4">
            <div className="mx-auto max-w-3xl">
              <PromptComposer onSubmit={(prompt, images, document, action) => submitPrompt(prompt, images, document, action)} disabled={loading || Boolean(quota)} />
              <p className="mt-2 text-center text-[11px] text-chat-muted">
                Proveri termine, cene i dostupnost pre odluke.
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
