import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../auth';
import { getUsage, type UsageSnapshot } from '../services/chat-api';
import { UsageContext, type UsageContextValue } from './UsageContextCore';

export const UsageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { session, isLoading: authLoading } = useAuth();
  const owner = authLoading ? 'loading' : session?.user.id ?? 'guest';
  const scope = useMemo(() => ({ owner }), [owner]);
  const activeScope = useRef(scope);
  useLayoutEffect(() => { activeScope.current = scope; }, [scope]);
  const [state, setState] = useState<{
    scope: { owner: string }; usage: UsageSnapshot | null; isLoading: boolean; error: string | null;
  }>();
  const usage = state?.scope === scope ? state.usage : null;
  const isLoading = state?.scope === scope ? state.isLoading : false;
  const error = state?.scope === scope ? state.error : null;

  const refreshUsage = useCallback(async (signal?: AbortSignal) => {
    if (authLoading || signal?.aborted || activeScope.current !== scope) return;
    setState((current) => ({ scope, usage: current?.scope === scope ? current.usage : null,
      isLoading: true, error: null }));

    try {
      const snapshot = await getUsage({ accessToken: session?.access_token, signal });
      if (!signal?.aborted && activeScope.current === scope) setState({ scope, usage: snapshot, isLoading: false, error: null });
    } catch {
      if (!signal?.aborted && activeScope.current === scope) setState((current) => ({
        scope, usage: current?.scope === scope ? current.usage : null,
        isLoading: false, error: 'Ne mogu da učitam potrošnju pitanja.',
      }));
    }
  }, [authLoading, scope, session?.access_token]);

  const applyUsageSnapshot = useCallback((snapshot: UsageSnapshot | null) => {
    if (!snapshot || activeScope.current !== scope) return;
    setState((current) => {
      const previous = current?.scope === scope ? current.usage : null;
      return {
        scope, isLoading: false, error: null,
        usage: { ...snapshot, identity: previous?.identity ?? snapshot.identity,
          reset_at: previous?.reset_at ?? snapshot.reset_at },
      };
    });
  }, [scope]);

  useEffect(() => {
    const request = new AbortController();
    void refreshUsage(request.signal);
    return () => request.abort();
  }, [refreshUsage, scope]);

  const value = useMemo<UsageContextValue>(() => ({
    usage, isLoading, error, refreshUsage, applyUsageSnapshot,
  }), [applyUsageSnapshot, error, isLoading, refreshUsage, usage]);

  return <UsageContext.Provider value={value}>{children}</UsageContext.Provider>;
};
