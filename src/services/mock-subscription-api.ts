import type { Session } from '@supabase/supabase-js';
import { API_BASE_URL } from '../constants/api';

export interface MockSubscriptionStatus {
  enabled: boolean;
  eligible: boolean;
  plan: 'free' | 'premium';
  is_mock: true;
}

export interface MockSubscriptionAction {
  status: 'active' | 'inactive';
  plan: 'free' | 'premium';
  is_mock: true;
  message: string;
}

export class MockSubscriptionError extends Error {
  status: number;
  code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = 'MockSubscriptionError';
    this.status = status;
    this.code = code;
  }
}

const authHeaders = (session: Session | null): Record<string, string> => {
  if (!session?.access_token) {
    throw new MockSubscriptionError('Sesija je istekla. Prijavi se ponovo.', 401);
  }

  return {
    Authorization: `Bearer ${session.access_token}`,
  };
};

const safeMessage = (status: number, payload: unknown) => {
  const detail = typeof payload === 'object' && payload ? (payload as { detail?: unknown }).detail : null;

  if (typeof detail === 'object' && detail && 'message' in detail && typeof detail.message === 'string') {
    return { message: detail.message, code: 'code' in detail && typeof detail.code === 'string' ? detail.code : null };
  }

  if (status === 401) {
    return { message: 'Sesija je istekla. Prijavi se ponovo.', code: null };
  }
  if (status === 403) {
    return { message: 'Demo Premium aktivacija nije dostupna za ovaj nalog.', code: null };
  }
  if (status === 404) {
    return { message: 'Demo Premium trenutno nije dostupan.', code: null };
  }

  return { message: 'Demo Premium trenutno nije dostupan. Pokušaj ponovo.', code: null };
};

const requestMockSubscription = async <T>(
  path: string,
  session: Session | null,
  method: 'GET' | 'POST',
): Promise<T> => {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: authHeaders(session),
    });
  } catch (error) {
    if (error instanceof MockSubscriptionError) {
      throw error;
    }
    throw new MockSubscriptionError('Mreža trenutno nije dostupna. Pokušaj ponovo.', 0);
  }

  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const { message, code } = safeMessage(response.status, payload);
    throw new MockSubscriptionError(message, response.status, code);
  }

  return response.json();
};

export const getMockSubscriptionStatus = (session: Session | null) =>
  requestMockSubscription<MockSubscriptionStatus>('/api/mock-subscription', session, 'GET');

export const activateMockPremium = (session: Session | null) =>
  requestMockSubscription<MockSubscriptionAction>('/api/mock-subscription/activate', session, 'POST');

export const deactivateMockPremium = (session: Session | null) =>
  requestMockSubscription<MockSubscriptionAction>('/api/mock-subscription/deactivate', session, 'POST');
