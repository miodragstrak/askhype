import { API_BASE_URL } from '../constants/api';
import type { ChatRequest, ChatResponse, DocumentAnalysisResponse, PendingImage } from '../types/chat';
import { getAnonymousId } from '../utils/anonymous-id';

interface BackendValidationError {
  detail?: unknown;
}

export interface UsageSnapshot {
  identity: 'guest' | 'authenticated';
  plan: 'guest' | 'free' | 'premium' | string;
  used: number;
  limit: number;
  remaining: number;
  reset_at: string | null;
}

export interface QuotaLimitPayload extends UsageSnapshot {
  code: 'prompt_limit_reached';
  message: string;
  actions: string[];
}

export interface ApiRequestOptions {
  accessToken?: string | null;
  signal?: AbortSignal;
}

export interface ChatApiResult {
  data: ChatResponse;
  usage: UsageSnapshot | null;
}

export interface DocumentApiResult {
  data: DocumentAnalysisResponse;
  usage: UsageSnapshot | null;
}

export interface XlsxTransformationApiResult {
  blob: Blob;
  filename: string;
  operation: string;
  summary: string;
  warnings: string[];
  usage: UsageSnapshot | null;
}

export interface PresentationApiResult {
  blob: Blob;
  filename: string;
  slideCount: number;
  summary: string;
  warnings: string[];
  usage: UsageSnapshot | null;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export class PromptLimitError extends ApiError {
  payload: QuotaLimitPayload;

  constructor(payload: QuotaLimitPayload) {
    super(payload.message || 'Iskoristio si dostupna AskHype pitanja.', 429);
    this.name = 'PromptLimitError';
    this.payload = payload;
  }
}

const getErrorMessage = (status: number, payload: BackendValidationError | null): string => {
  if (status >= 400 && status < 500 && typeof payload?.detail === 'string') {
    return payload.detail;
  }
  if (status === 422 && Array.isArray(payload?.detail)) {
    const firstError = payload.detail[0];
    if (
      firstError &&
      typeof firstError === 'object' &&
      'msg' in firstError &&
      typeof firstError.msg === 'string'
    ) {
      return firstError.msg;
    }
  }

  if (status >= 500) {
    return 'AskHype trenutno ne može da odgovori. Proveri da li je backend pokrenut i pokušaj ponovo.';
  }

  return 'Ne mogu da pošaljem poruku. Proveri unos i pokušaj ponovo.';
};

const isQuotaLimitPayload = (value: unknown): value is QuotaLimitPayload => {
  if (!value || typeof value !== 'object') return false;
  const payload = value as Partial<QuotaLimitPayload>;
  return (
    payload.code === 'prompt_limit_reached' &&
    typeof payload.message === 'string' &&
    typeof payload.identity === 'string' &&
    typeof payload.plan === 'string' &&
    typeof payload.used === 'number' &&
    typeof payload.limit === 'number' &&
    typeof payload.remaining === 'number' &&
    Array.isArray(payload.actions)
  );
};

const readUsageHeaders = (response: Response): UsageSnapshot | null => {
  const plan = response.headers.get('X-AskHype-Plan');
  const used = Number(response.headers.get('X-AskHype-Usage-Used'));
  const limit = Number(response.headers.get('X-AskHype-Usage-Limit'));
  const remaining = Number(response.headers.get('X-AskHype-Usage-Remaining'));

  if (!plan || !Number.isFinite(used) || !Number.isFinite(limit) || !Number.isFinite(remaining)) {
    return null;
  }

  return {
    identity: plan === 'guest' ? 'guest' : 'authenticated',
    plan,
    used,
    limit,
    remaining,
    reset_at: null,
  };
};

const authHeaders = (accessToken?: string | null): Record<string, string> => {
  if (accessToken) {
    return { Authorization: `Bearer ${accessToken}` };
  }

  return { 'X-Anonymous-ID': getAnonymousId() };
};

export const sendChatMessage = async (
  request: ChatRequest,
  options: ApiRequestOptions = {},
  images: PendingImage[] = [],
): Promise<ChatApiResult> => {
  let response: Response;

  try {
    const body = images.length ? new FormData() : JSON.stringify(request);
    const headers = authHeaders(options.accessToken);
    if (body instanceof FormData) {
      body.append('request', JSON.stringify(request));
      images.forEach(({ file }) => body.append('images', file));
    } else {
      headers['Content-Type'] = 'application/json';
    }
    response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: 'POST',
      headers,
      body,
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Zahtev je otkazan.');
    }

    throw new ApiError(
      'AskHype trenutno ne može da odgovori. Proveri da li je backend pokrenut i pokušaj ponovo.',
      0,
    );
  }

  if (!response.ok) {
    let payload: BackendValidationError | null = null;

    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (response.status === 429 && isQuotaLimitPayload(payload?.detail)) {
      throw new PromptLimitError(payload.detail);
    }

    throw new ApiError(getErrorMessage(response.status, payload), response.status);
  }

  return {
    data: await response.json(),
    usage: readUsageHeaders(response),
  };
};

export const sendDocumentAnalysis = async (
  file: File,
  prompt: string,
  options: ApiRequestOptions = {},
): Promise<DocumentApiResult> => {
  const body = new FormData();
  body.append('file', file);
  body.append('prompt', prompt);
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}/api/documents/analyze`, {
      method: 'POST',
      headers: authHeaders(options.accessToken),
      body,
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Zahtev je otkazan.');
    }
    throw new ApiError('Dokument trenutno nije moguće analizirati. Pokušaj ponovo.', 0);
  }

  if (!response.ok) {
    let payload: BackendValidationError | null = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (response.status === 429 && isQuotaLimitPayload(payload?.detail)) {
      throw new PromptLimitError(payload.detail);
    }
    throw new ApiError(getErrorMessage(response.status, payload), response.status);
  }

  return { data: await response.json(), usage: readUsageHeaders(response) };
};

const decodedHeader = (response: Response, name: string, fallback: string): string => {
  const value = response.headers.get(name);
  if (!value) return fallback;
  try { return decodeURIComponent(value); } catch { return fallback; }
};

export const sendXlsxTransformation = async (
  file: File,
  instruction: string,
  options: ApiRequestOptions = {},
): Promise<XlsxTransformationApiResult> => {
  const body = new FormData();
  body.append('file', file);
  body.append('instruction', instruction);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/documents/transform-xlsx`, {
      method: 'POST', headers: authHeaders(options.accessToken), body, signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('Zahtev je otkazan.');
    throw new ApiError('Excel dokument trenutno nije moguće izmeniti. Pokušaj ponovo.', 0);
  }
  if (!response.ok) {
    let payload: BackendValidationError | null = null;
    try { payload = await response.json(); } catch { payload = null; }
    if (response.status === 429 && isQuotaLimitPayload(payload?.detail)) throw new PromptLimitError(payload.detail);
    throw new ApiError(getErrorMessage(response.status, payload), response.status);
  }
  const warningHeader = decodedHeader(response, 'X-AskHype-Transformation-Warnings', '[]');
  let warnings: string[] = [];
  try {
    const parsed: unknown = JSON.parse(warningHeader);
    if (Array.isArray(parsed)) warnings = parsed.filter((item): item is string => typeof item === 'string');
  } catch { warnings = []; }
  return {
    blob: await response.blob(),
    filename: decodedHeader(response, 'X-AskHype-Output-Filename', 'workbook_transformed.xlsx'),
    operation: response.headers.get('X-AskHype-Transformation-Operation') || 'transformation',
    summary: decodedHeader(response, 'X-AskHype-Transformation-Summary', 'Excel dokument je uspešno izmenjen.'),
    warnings,
    usage: readUsageHeaders(response),
  };
};

export const sendPresentationGeneration = async (
  prompt: string,
  file: File | null,
  options: ApiRequestOptions = {},
): Promise<PresentationApiResult> => {
  const body = new FormData();
  body.append('prompt', prompt);
  if (file) body.append('file', file);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/presentations/generate`, {
      method: 'POST', headers: authHeaders(options.accessToken), body, signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('Zahtev je otkazan.');
    throw new ApiError('PowerPoint prezentaciju trenutno nije moguće napraviti. Pokušaj ponovo.', 0);
  }
  if (!response.ok) {
    let payload: BackendValidationError | null = null;
    try { payload = await response.json(); } catch { payload = null; }
    if (response.status === 429 && isQuotaLimitPayload(payload?.detail)) throw new PromptLimitError(payload.detail);
    throw new ApiError(getErrorMessage(response.status, payload), response.status);
  }
  const warningHeader = decodedHeader(response, 'X-AskHype-Presentation-Warnings', '[]');
  let warnings: string[] = [];
  try {
    const parsed: unknown = JSON.parse(warningHeader);
    if (Array.isArray(parsed)) warnings = parsed.filter((item): item is string => typeof item === 'string');
  } catch { warnings = []; }
  return {
    blob: await response.blob(),
    filename: decodedHeader(response, 'X-AskHype-Output-Filename', 'askhype_presentation.pptx'),
    slideCount: Number(response.headers.get('X-AskHype-Presentation-Slide-Count')) || 0,
    summary: decodedHeader(response, 'X-AskHype-Presentation-Summary', 'PowerPoint prezentacija je napravljena.'),
    warnings,
    usage: readUsageHeaders(response),
  };
};

export const getUsage = async (options: ApiRequestOptions = {}): Promise<UsageSnapshot> => {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}/api/usage`, {
      headers: authHeaders(options.accessToken),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('Zahtev je otkazan.', 0);
    }

    throw new ApiError('AskHype kvote trenutno nisu dostupne. Pokušaj ponovo.', 0);
  }

  if (!response.ok) {
    let payload: BackendValidationError | null = null;

    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    throw new ApiError(getErrorMessage(response.status, payload), response.status);
  }

  return response.json();
};
