import { API_BASE_URL } from '../constants/api';
import type { ChatRequest, ChatResponse } from '../types/chat';

interface BackendValidationError {
  detail?: unknown;
}

const getErrorMessage = (status: number, payload: BackendValidationError | null): string => {
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

export const sendChatMessage = async (
  request: ChatRequest,
  signal?: AbortSignal
): Promise<ChatResponse> => {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Zahtev je otkazan.');
    }

    throw new Error(
      'AskHype trenutno ne može da odgovori. Proveri da li je backend pokrenut i pokušaj ponovo.'
    );
  }

  if (!response.ok) {
    let payload: BackendValidationError | null = null;

    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    throw new Error(getErrorMessage(response.status, payload));
  }

  return response.json();
};
