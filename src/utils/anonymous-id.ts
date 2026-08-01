const ANONYMOUS_ID_KEY = 'askhype.anonymousId';
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const fallbackRandomId = () =>
  '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, (character) =>
    (
      Number(character) ^
      (Math.random() * 16) >> (Number(character) / 4)
    ).toString(16),
  );

const createAnonymousId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  return fallbackRandomId();
};

export const getAnonymousId = () => {
  try {
    const current = localStorage.getItem(ANONYMOUS_ID_KEY);
    if (current && UUID_PATTERN.test(current)) {
      return current;
    }

    const nextId = createAnonymousId();
    localStorage.setItem(ANONYMOUS_ID_KEY, nextId);
    return nextId;
  } catch {
    return createAnonymousId();
  }
};
