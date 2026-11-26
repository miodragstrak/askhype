import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { History, Plus, UserRound } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth';
import { ApiError, PromptLimitError, readDurableChatTurn, submitDurableChatTurn, type DurableChatTurn, startResearch, sendChatMessage, sendDocumentAnalysis, sendGenerativeSvgAnimation, sendPresentationGeneration, sendXlsxTransformation, type QuotaLimitPayload } from '../../services/chat-api';
import { ResearchProgress, useResearchJobs } from './ResearchProgress';
import type { LocalConversation, LocalMessage } from '../../types/conversation';
import type { ChatRequest, ChatResponse, DocumentAction, PendingDocument, PendingImage } from '../../types/chat';
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
import {
  HISTORY_PAGE_SIZE,
  initializeAuthenticatedHistory,
  SupabaseConversationRepository,
} from '../../services/conversation-repository';
import { HistoryError, historyDiagnostic, historyErrorCategory } from '../../services/history-diagnostics';
import { clearConversations, migrationMarkerKey } from '../../utils/conversation-storage';

const createId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const researchResultId = (messageId: string) =>
  messageId.slice(0, -1) + (Number.parseInt(messageId.slice(-1), 16) ^ 1).toString(16);

const serverTurnsEnabled = import.meta.env.VITE_SERVER_CHAT_TURNS_ENABLED === 'true';
type DurableSubmission = { id: string; create: boolean; request: ChatRequest };
type DurableStatus = DurableChatTurn['status'] | 'missing';

export const AskHypeShell = () => {
  const { user, isLoading } = useAuth();
  return <AccountConversationShell key={isLoading ? 'loading' : user?.id ?? 'guest'} />;
};

const AccountConversationShell = () => {
  const navigate = useNavigate();
  const { session, user, profile, isLoading: authLoading } = useAuth();
  const { usage, applyUsageSnapshot, refreshUsage } = useUsage();
  const userId = user?.id;
  const durableHistory = serverTurnsEnabled && Boolean(userId);
  const auth = authLoading ? "loading" : userId ? "account" : "guest";
  const [conversations, setConversations] = useState<LocalConversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [researchRevision, setResearchRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaLimitPayload | null>(null);
  const [historyOwner, setHistoryOwner] = useState<string | null>(null);
  const [persistenceNotice, setPersistenceNotice] = useState<string | null>(null);
  const [lastSubmission, setLastSubmission] = useState<{ conversationId: string; text: string; images: PendingImage[]; document: PendingDocument | null; documentAction: DocumentAction; animationDuration: number; durable?: DurableSubmission } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const preferences = useMemo(() => storageUtils.getUserPreferences(), []);
  const [unsavedIds, setUnsavedIds] = useState<ReadonlySet<string>>(() => new Set());
  const [saving, setSaving] = useState(false);
  const accountScope = useRef(new AbortController());
  const token = useRef(session?.access_token);
  const navigation = useRef(0);
  const confirmedConversations = useRef(new Set<string>());
  const deleted = useRef(new Set<string>());
  const pendingWrites = useRef(new Map<string, Promise<unknown>>());
  const submitting = useRef(false);
  const [turnStatuses, setTurnStatuses] = useState<Record<string, DurableStatus>>({});
  const [historyCursor, setHistoryCursor] = useState<LocalConversation | null>(null);
  const [messagePages, setMessagePages] = useState<Record<string, { cursor: LocalMessage | undefined; more: boolean }>>({});
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageRetry, setPageRetry] = useState(0);
  const [paging, setPaging] = useState(false);

  useLayoutEffect(() => {
    const scope = new AbortController();
    accountScope.current = scope;
    historyDiagnostic('auth_transition', auth)();
    return () => scope.abort();
  }, [auth]);
  useLayoutEffect(() => { token.current = session?.access_token; }, [session?.access_token]);

  const conversationRepository = useMemo(() => new SupabaseConversationRepository(() => {
    if (accountScope.current.signal.aborted) throw new HistoryError('stale');
    if (!token.current) throw new HistoryError('authentication');
    return { token: token.current, signal: accountScope.current.signal };
  }, durableHistory), [durableHistory]);
  const markUnsaved = (id: string, failed: boolean) => setUnsavedIds((current) => {
    const next = new Set(current);
    if (failed) next.add(id);
    else next.delete(id);
    return next;
  });
  const trackWrite = (id: string, write: Promise<unknown>) => {
    pendingWrites.current.set(id, write);
    void write.finally(() => {
      if (pendingWrites.current.get(id) === write) pendingWrites.current.delete(id);
    });
  };

  async function historyOperation<T>(
    operation: Parameters<typeof historyDiagnostic>[0], id: string, action: () => Promise<T>,
  ): Promise<T> {
    const report = historyDiagnostic(operation, auth, id);
    try {
      const value = await action();
      report();
      return value;
    } catch (error) {
      report(historyErrorCategory(error));
      throw error;
    }
  }
  const activeConversation = conversations.find((conversation) => conversation.id === activeId) ?? null;
  const research = useResearchJobs(user && historyOwner === user.id ? activeId : null, session?.access_token, researchRevision);

  const loaded = Boolean(activeId && messagePages[activeId]);
  const needsMessages = durableHistory && Boolean(activeId && confirmedConversations.current.has(activeId)) && !loaded;
  const outstanding = durableHistory
    ? activeConversation?.messages.findLast((message) => message.role === 'user' && message.ordinaryTurn)
    : undefined;
  const completedInHistory = activeConversation?.messages.some(
    (message) => message.role === 'assistant' && message.ordinaryTurnId === outstanding?.id,
  );
  const turnId = outstanding && !completedInHistory ? outstanding.id : undefined;
  const turnStatus = turnId ? turnStatuses[turnId] : undefined;
  const waitingForTurn = Boolean(turnId && (!turnStatus || turnStatus === 'processing'));

  const receiveTurn = useCallback((turn: DurableChatTurn) => {
    if (accountScope.current.signal.aborted || deleted.current.has(turn.conversation_id)) return;
    confirmedConversations.current.add(turn.conversation_id);
    setTurnStatuses((current) => ({ ...current, [turn.id]: turn.status }));
    if (!turn.response || turn.status !== 'completed') return;
    const reply: LocalMessage = {
      id: turn.assistant_message_id, role: 'assistant', response: turn.response,
      ordinaryTurnId: turn.id, createdAt: turn.completed_at ?? turn.created_at,
    };
    setConversations((current) => sortConversations(current.map((item) => item.id !== turn.conversation_id ? item : {
      ...item, updatedAt: Date.parse(reply.createdAt) > Date.parse(item.updatedAt) ? reply.createdAt : item.updatedAt,
      serverConversationId: reply.response.conversation_id,
      messages: item.messages.some((message) => message.id === reply.id) ? item.messages : [...item.messages, reply],
    })));
    void refreshUsage();
  }, [refreshUsage]);

  useEffect(() => {
    if (!needsMessages || !activeId) return;
    const signal = accountScope.current.signal;
    let stale = false;
    setPageError(null);
    void conversationRepository.listMessagePage(activeId).then(({ items, more }) => {
      if (stale || signal.aborted || deleted.current.has(activeId)) return;
      setConversations((current) => current.map((item) => item.id !== activeId ? item : {
        ...item, messages: [...items, ...item.messages.filter((message) => !items.some((saved) => saved.id === message.id))],
      }));
      setMessagePages((current) => ({ ...current, [activeId]: { cursor: items[0], more } }));
    }).catch(() => {
      if (!stale && !signal.aborted) setPageError('Poruke trenutno nisu dostupne.');
    });
    return () => { stale = true; };
  }, [activeId, conversationRepository, needsMessages, pageRetry]);

  useEffect(() => {
    if (!durableHistory || !turnId || !activeId || !waitingForTurn || loading || needsMessages) return;
    const request = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const deadline = Date.now() + 200_000;
    const poll = async () => {
      try {
        const result = await readDurableChatTurn(turnId, {
          accessToken: token.current, signal: AbortSignal.any([request.signal, AbortSignal.timeout(8000)]),
        });
        if (request.signal.aborted || result.conversation_id !== activeId) return;
        receiveTurn(result);
        if (result.status !== 'processing') return;
      } catch (failure) {
        if (request.signal.aborted) return;
        if (failure instanceof ApiError && failure.status === 404) {
          setTurnStatuses((current) => ({ ...current, [turnId]: 'missing' }));
          return;
        }
      }
      if (!request.signal.aborted && Date.now() < deadline) timer = setTimeout(poll, 2000);
      else if (!request.signal.aborted) setPageError('Status poruke trenutno nije dostupan. Osveži stranicu.');
    };
    void poll();
    return () => { request.abort(); clearTimeout(timer); };
  }, [activeId, durableHistory, loading, needsMessages, receiveTurn, turnId, waitingForTurn]);

  const loadOlderThreads = async () => {
    if (!historyCursor || paging) return;
    const signal = accountScope.current.signal;
    setPaging(true);
    try {
      const { items, more } = await conversationRepository.listConversationPage(historyCursor);
      if (signal.aborted) return;
      const visible = items.filter((item) => !deleted.current.has(item.id));
      visible.forEach((item) => confirmedConversations.current.add(item.id));
      setConversations((current) => sortConversations([
        ...current, ...visible.filter((item) => !current.some((thread) => thread.id === item.id)),
      ]));
      setHistoryCursor(more ? items.at(-1) ?? null : null);
    } catch {
      if (!signal.aborted) setPersistenceNotice('Stariji razgovori trenutno nisu dostupni.');
    } finally {
      if (!signal.aborted) setPaging(false);
    }
  };

  const loadOlderMessages = async (id: string, cursor: LocalMessage) => {
    if (paging) return;
    const signal = accountScope.current.signal;
    const version = navigation.current;
    setPaging(true);
    try {
      const { items, more } = await conversationRepository.listMessagePage(id, cursor);
      if (signal.aborted || deleted.current.has(id)) return;
      setConversations((current) => current.map((item) => item.id !== id ? item : {
        ...item, messages: [...items.filter((message) => !item.messages.some((saved) => saved.id === message.id)), ...item.messages],
      }));
      setMessagePages((current) => ({ ...current, [id]: { cursor: items[0] ?? cursor, more } }));
    } catch {
      if (!signal.aborted && navigation.current === version) setPersistenceNotice('Starije poruke trenutno nisu dostupne.');
    } finally {
      if (!signal.aborted) setPaging(false);
    }
  };

  useEffect(() => {
    if (historyOwner === 'guest') saveConversations(conversations);
  }, [conversations, historyOwner]);

  useEffect(() => {
    if (historyOwner === 'guest') saveActiveConversationId(activeId);
  }, [activeId, historyOwner]);

  useEffect(() => {
    if (authLoading) return;
    let cancelled = false;
    const signal = accountScope.current.signal;
    const stale = () => cancelled || signal.aborted;
    const report = historyDiagnostic('hydrate', auth);
    setHistoryOwner(null);
    setPersistenceNotice(null);

    const initialize = async () => {
      if (!userId) {
        const local = loadConversations();
        if (stale()) return;
        setConversations(local);
        setActiveId(loadActiveConversationId(local));
        setHistoryOwner('guest');
        report();
        return;
      }

      try {
        const marker = migrationMarkerKey(userId);
        let storedMigrationState: string | null = null;
        let storageAvailable = true;
        try { storedMigrationState = localStorage.getItem(marker); }
        catch { storageAvailable = false; historyDiagnostic('hydrate', auth)('cache'); }
        const migrationState = storedMigrationState === 'complete' || storedMigrationState === 'in_progress'
          ? storedMigrationState
          : null;
        const local = !storageAvailable || migrationState === 'complete' ? [] : loadConversations();
        const initialized = await initializeAuthenticatedHistory(
          conversationRepository,
          local,
          migrationState,
          () => {
            if (stale()) throw new HistoryError('stale');
            // If the marker is unavailable, skip the import and continue with server history.
            try { localStorage.setItem(marker, 'in_progress'); }
            catch {
              storageAvailable = false;
              historyDiagnostic('hydrate', auth)('cache');
              return false;
            }
          },
        );
        const serverConversations = initialized.conversations;
        if (stale()) { report('stale'); return; }
        if (storageAvailable && migrationState !== 'complete') {
          try {
            localStorage.setItem(marker, 'complete');
            if (initialized.migrated) clearConversations();
          } catch { historyDiagnostic('hydrate', auth)('cache'); }
        }
        confirmedConversations.current = new Set(serverConversations.map((conversation) => conversation.id));
        setConversations(serverConversations);
        setHistoryCursor(durableHistory && serverConversations.length === HISTORY_PAGE_SIZE
          ? serverConversations.at(-1) ?? null : null);
        setActiveId((current) =>
          serverConversations.some((conversation) => conversation.id === current)
            ? current
            : serverConversations[0]?.id ?? null,
        );
        historyDiagnostic('order', auth)();
        report();
      } catch (error) {
        report(stale() ? 'stale' : historyErrorCategory(error));
        if (!stale()) {
          setPersistenceNotice('Istorija razgovora trenutno nije dostupna. Novi razgovor ostaje otvoren u ovoj sesiji.');
        }
      } finally {
        if (!stale()) setHistoryOwner(userId);
      }
    };

    void initialize();
    return () => { cancelled = true; };
  }, [auth, authLoading, conversationRepository, durableHistory, userId]);

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
    animationDuration = 20,
    options: { appendUser?: boolean; conversationId?: string; durable?: DurableSubmission } = {},
  ): Promise<boolean> => {
    const visiblePrompt = rawPrompt.trim();
    const prompt = visiblePrompt || (images.length ? 'Analiziraj priloženu sliku/slike i opiši relevantne informacije.' : '');
    const signal = accountScope.current.signal;
    if (!prompt || submitting.current || saving || historyOwner === null || signal.aborted
        || needsMessages || (waitingForTurn && !options.durable)
        || (document && images.length > 0)) return false;
    if (turnStatus === 'missing' && activeId && !confirmedConversations.current.has(activeId) && !options.durable) {
      return false;
    }
    submitting.current = true;

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
    const chatRequest: ChatRequest = {
      message: prompt, conversation_id: conversation.serverConversationId,
      location: preferences.city || 'Beograd', language: preferences.language || 'sr',
      interests: preferences.interests ?? [], history,
    };
    const durable = durableHistory && !document && documentAction === 'analyze'
      ? options.durable ?? { id: createId(), create: !confirmedConversations.current.has(conversation.id), request: chatRequest }
      : undefined;
    const userMessage: LocalMessage = {
      id: durable?.id ?? createId(),
      ordinaryTurn: durable ? true : undefined,
      role: 'user',
      text: visiblePrompt || 'Priložena slika',
      imagePreviews: images.map((image) => image.previewUrl),
      documentName: document?.file.name,
      documentType: document?.file.name.split('.').pop()?.toLocaleUpperCase(),
      documentAction: document || documentAction === 'animation' ? documentAction : undefined,
      createdAt: now,
    };
    const pendingConversation = {
      ...conversation,
      updatedAt: now,
      messages: appendUser ? [...conversation.messages, userMessage] : conversation.messages,
    };

    const stillOwned = () => !signal.aborted && !deleted.current.has(conversation.id);
    const assertOwned = () => { if (!stillOwned()) throw new HistoryError('stale'); };
    const openVersion = ++navigation.current;
    const requestOptions = { accessToken: session?.access_token, signal };
    setActiveId(conversation.id);
    upsertConversation(pendingConversation);
    setLastSubmission({ conversationId: conversation.id, text: prompt, images, document, documentAction, animationDuration, durable });
    setLoading(true);
    setError(null);
    setQuota(null);

    const persistedUser = appendUser ? userMessage : conversation.messages.findLast((message) => message.role === 'user');
    const persistUserMessage = userId && !durable
      ? (async () => {
          try {
            assertOwned();
            // Initial creation is idempotent. A retry may follow a failed create.
            if (!confirmedConversations.current.has(conversation.id)) {
              await historyOperation('create', conversation.id, () => conversationRepository.createConversation(pendingConversation));
              confirmedConversations.current.add(conversation.id);
            }
            assertOwned();
            if (persistedUser) {
              await historyOperation('save_user', conversation.id, () =>
                conversationRepository.appendMessage(conversation.id, persistedUser));
            }
            assertOwned();
            await historyOperation('update', conversation.id, () =>
              conversationRepository.updateConversation(conversation.id, { updatedAt: now }));
            return stillOwned();
          } catch {
            if (stillOwned()) markUnsaved(conversation.id, true);
            return false;
          }
        })()
      : Promise.resolve(false);
    if (userId && !durable) trackWrite(conversation.id, persistUserMessage);

    try {
      let result;
      if (documentAction === 'animation') {
        const animation = await sendGenerativeSvgAnimation(prompt, animationDuration, requestOptions);
        const data: ChatResponse = {
          conversation_id: conversation.serverConversationId || `generative_svg_${createId()}`,
          provider: 'gemini', answer_type: 'generative_svg_animation',
          summary: 'AI animacija je spremna.', recommendations: [],
          follow_up_actions: [], sources: [], generated_at: animation.generated_at,
          generative_svg_storyboard: animation,
          animation_quota_remaining: animation.remaining_quota,
        };
        result = { data, usage: null };
      } else if (documentAction === 'research') {
        try {
          if (!userId || !await persistUserMessage) throw new Error('Sačuvajte razgovor na nalogu pre pokretanja istraživanja.');
          assertOwned();
          await startResearch(prompt, document?.file ?? null, {
            accessToken: session?.access_token, conversationId: conversation.id,
            // Reserve a different UUID from the user message for the durable assistant result.
            requestId: researchResultId(!appendUser && lastMessage?.role === 'user' ? lastMessage.id : userMessage.id),
            signal: AbortSignal.any([signal, AbortSignal.timeout(90_000)]),
          });
          return true;
        } finally {
          if (stillOwned()) setResearchRevision((value) => value + 1);
        }
      } else if (documentAction === 'presentation') {
        const presentation = await sendPresentationGeneration(
          prompt, document?.file ?? null, requestOptions,
        );
        assertOwned();
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
            document.file, prompt, requestOptions,
          );
          assertOwned();
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
          requestOptions,
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
      } else if (durable) {
        const submission = submitDurableChatTurn(durable.id, conversation.id, durable.create, durable.request,
          requestOptions, images);
        trackWrite(conversation.id, submission.catch(() => undefined));
        const turn = await submission;
        assertOwned();
        if (turn.id !== durable.id || turn.conversation_id !== conversation.id) throw new HistoryError('stale');
        setMessagePages((current) => current[conversation.id] ? current : {
          ...current, [conversation.id]: { cursor: undefined, more: false },
        });
        receiveTurn(turn);
        return true;
      } else {
        result = await sendChatMessage(chatRequest, requestOptions, images);
      }
      assertOwned();
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
      if (userId) {
        const write = persistUserMessage.then(async (userMessageSaved) => {
          if (!userMessageSaved || !stillOwned()) return;
          try {
            await historyOperation('save_assistant', conversation.id, () =>
              conversationRepository.appendMessage(conversation.id, assistantMessage));
            assertOwned();
            await historyOperation('update', conversation.id, () => conversationRepository.updateConversation(conversation.id, {
              updatedAt: assistantMessage.createdAt, serverConversationId: result.data.conversation_id,
            }));
          } catch {
            if (stillOwned()) markUnsaved(conversation.id, true);
          }
        });
        trackWrite(conversation.id, write);
        await write;
      }
      assertOwned();
      applyUsageSnapshot(result.usage);
      void refreshUsage();
      return true;
    } catch (requestError) {
      if (!stillOwned()) {
        historyDiagnostic('accept_response', auth, conversation.id)('stale');
        return false;
      }
      if (durable && requestError instanceof ApiError && requestError.status < 500) {
        setTurnStatuses((current) => ({ ...current, [durable.id]: 'missing' }));
      }
      if (openVersion !== navigation.current) return false;
      if (requestError instanceof PromptLimitError) {
        setQuota(requestError.payload);
        applyUsageSnapshot(requestError.payload);
      } else {
        setError(durable ? 'Status poruke trenutno nije dostupan. Proveravamo da li je poruka sačuvana.'
          : requestError instanceof Error ? requestError.message : 'AskHype trenutno ne može da odgovori. Pokušaj ponovo.');
      }
      return false;
    } finally {
      submitting.current = false;
      if (!signal.aborted) setLoading(false);
    }
  };

  const startNew = () => {
    navigation.current += 1;
    setActiveId(null);
    setError(null);
    setQuota(null);
    setSidebarOpen(false);
  };

  const selectConversation = (id: string) => {
    const report = historyDiagnostic('open', auth, id);
    if (!conversations.some((item) => item.id === id) || deleted.current.has(id)) {
      report('missing');
      return;
    }
    navigation.current += 1;
    setActiveId(id);
    report();
    setError(null);
    setQuota(null);
    setSidebarOpen(false);
  };

  const deleteConversation = (id: string) => {
    deleted.current.add(id);
    setConversations((current) => current.filter((conversation) => conversation.id !== id));
    markUnsaved(id, false);
    if (activeId === id) startNew();
    if (userId) {
      const signal = accountScope.current.signal;
      void (async () => {
        await pendingWrites.current.get(id);
        if (signal.aborted) return;
        try {
          await historyOperation('delete', id, () => conversationRepository.deleteConversation(id));
        } catch {
          if (!signal.aborted) setPersistenceNotice('Razgovor je uklonjen sa ekrana, ali brisanje sa naloga trenutno nije potvrđeno.');
        }
      })();
    } else {
      historyDiagnostic('delete', auth, id)();
    }
  };

  const retrySave = (conversation: LocalConversation) => {
    if (saving || submitting.current || !userId) return;
    const signal = accountScope.current.signal;
    const current = () => !signal.aborted && !deleted.current.has(conversation.id);
    if (!current()) return;
    setSaving(true);
    const write = historyOperation('save_retry', conversation.id, async () => {
      if (!confirmedConversations.current.has(conversation.id)) {
        await conversationRepository.createConversation(conversation);
        confirmedConversations.current.add(conversation.id);
      }
      for (const message of conversation.messages) {
        if (!current()) throw new HistoryError('stale');
        if (message.role === 'user' ? message.ordinaryTurn : message.ordinaryTurnId) continue;
        await conversationRepository.appendMessage(conversation.id, message);
      }
      if (!current()) throw new HistoryError('stale');
      await conversationRepository.updateConversation(conversation.id, {
        updatedAt: conversation.updatedAt, serverConversationId: conversation.serverConversationId,
      });
    }).then(() => {
      if (current()) markUnsaved(conversation.id, false);
    }).catch(() => {
      // The unsaved notice remains visible and can be retried.
    }).finally(() => {
      if (!signal.aborted) setSaving(false);
    });
    trackWrite(conversation.id, write);
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
          unsavedIds={unsavedIds}
          onLoadOlder={historyCursor ? () => void loadOlderThreads() : undefined}
          paging={paging}
          activeId={activeId}
          mobileOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNew={startNew}
          onSelect={selectConversation}
          onDelete={deleteConversation}
        />

        <main className="flex min-w-0 flex-1 flex-col bg-chat-bg">
          <div className="min-h-0 flex-1 overflow-y-auto">
            {durableHistory && historyOwner === null && <p className="px-5 py-4" role="status">Učitavanje razgovora…</p>}
            {needsMessages && <p className="px-5 py-4" role="status">{pageError ?? 'Učitavanje poruka…'}
              {pageError && <button className="ml-2 underline" onClick={() => setPageRetry((value) => value + 1)}>Ponovi učitavanje</button>}
            </p>}
            {activeId && messagePages[activeId]?.more && messagePages[activeId].cursor && (
              <button type="button" className="mx-auto block py-3 text-sm underline" disabled={paging}
                onClick={() => { const cursor = messagePages[activeId].cursor; if (cursor) void loadOlderMessages(activeId, cursor); }}>
                Prikaži starije poruke
              </button>
            )}
            {activeConversation?.messages.length ? (
              <ConversationThread
                messages={[...activeConversation.messages, ...(research.jobs ?? []).flatMap((job): LocalMessage[] => {
                  const report = job.result;
                  if (!report || activeConversation.messages.some((message) => message.id === job.research_id)) return [];
                  return [{
                    id: job.research_id, role: 'assistant', createdAt: report.generated_at,
                    response: {
                      conversation_id: activeConversation.serverConversationId ?? `research_${job.research_id}`,
                      provider: report.provider, answer_type: 'deep_research', summary: report.summary,
                      generated_at: report.generated_at, research: report,
                      sources: report.sources, recommendations: [], follow_up_actions: [],
                    },
                  }];
                })].sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt))}
                loading={(loading && lastSubmission?.documentAction !== 'research') || waitingForTurn}
                loadingLabel={lastSubmission?.documentAction === 'animation' ? 'AskHype kreira animaciju…' : undefined}
                error={lastSubmission?.conversationId !== activeId ? null : lastSubmission?.durable
                  ? (turnStatus === 'missing' && !quota ? 'Čuvanje poruke nije potvrđeno. Ponovi isti zahtev ili započni novi razgovor.' : null)
                  : error}
                quota={quota}
                onRetry={() => {
                  if (lastSubmission && lastSubmission.conversationId === activeId) {
                    void submitPrompt(lastSubmission.text, lastSubmission.images, lastSubmission.document, lastSubmission.documentAction, lastSubmission.animationDuration, {
                      appendUser: false,
                      conversationId: lastSubmission.conversationId, durable: lastSubmission.durable,
                    });
                  }
                }}
                onFollowUp={(prompt) => void submitPrompt(prompt)}
                onSignIn={() => authNavigate('signIn')}
                onSignUp={() => authNavigate('signUp')}
                onPremium={() => navigate('/premium')}
              />
            ) : !needsMessages && (!durableHistory || historyOwner !== null) ? (
              <EmptyConversation />
            ) : null}
            <div className="mx-auto max-w-3xl px-3">
              {loading && lastSubmission?.documentAction === 'research' && lastSubmission.conversationId === activeId && (
                <p role="status">Deep Research · Slanje zahteva…</p>
              )}
              {turnStatus === 'unknown' && <p role="status">Ishod prethodne poruke nije potvrđen. Zahtev nije ponovljen.</p>}
              {turnStatus === 'failed' && <p role="status">Prethodna poruka je sačuvana, ali odgovor nije uspeo.</p>}
              {pageError && !needsMessages && <p role="status">{pageError}</p>}
              {research.jobs?.filter((job) => job.status !== 'completed').map((job) => (
                <ResearchProgress key={job.research_id} job={job} />
              ))}
              {research.offline && <p role="status">Status istraživanja trenutno nije dostupan.{' '}
                <button type="button" className="underline" onClick={research.retry}>Osveži status</button>
              </p>}
            </div>
            <div ref={bottomRef} />
          </div>

          <div className="flex-none border-t border-chat-border bg-chat-bg px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-6 sm:pb-4">
            <div className="mx-auto max-w-3xl">
              <PromptComposer onSubmit={(prompt, images, document, action, duration) => submitPrompt(prompt, images, document, action, duration)} disabled={loading || saving || needsMessages || waitingForTurn || Boolean(quota) || authLoading || historyOwner === null} />
              <p className="mt-2 text-center text-[11px] text-chat-muted">
                Proveri termine, cene i dostupnost pre odluke.
              </p>
              {activeConversation && unsavedIds.has(activeConversation.id) && (
                <p className="mt-1 text-center text-xs text-chat-muted" role="status">
                  Razgovor nije u potpunosti sačuvan na nalogu.{' '}
                  <button type="button" className="underline" disabled={loading || saving}
                    onClick={() => retrySave(activeConversation)}>Ponovi čuvanje</button>
                </p>
              )}
              {persistenceNotice && (
                <p className="mt-1 text-center text-[11px] text-chat-muted" role="status">
                  {persistenceNotice}
                </p>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
