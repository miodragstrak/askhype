import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth';
import { ApiError, getUsage, type UsageSnapshot } from '../services/chat-api';
import { UsageContext, type UsageContextValue } from './UsageContextCore';

export const UsageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { session, isLoading: authLoading } = useAuth();
  const [usage, setUsage] = useState<UsageSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshUsage = useCallback(async () => {
    if (authLoading) return;

    setIsLoading(true);
    setError(null);

    try {
      const snapshot = await getUsage({ accessToken: session?.access_token });
      setUsage(snapshot);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.message === 'Zahtev je otkazan.') {
        return;
      }

      setError('Ne mogu da učitam potrošnju pitanja.');
    } finally {
      setIsLoading(false);
    }
  }, [authLoading, session?.access_token]);

  const applyUsageSnapshot = useCallback((snapshot: UsageSnapshot | null) => {
    if (!snapshot) return;
    setUsage((current) => ({
      ...snapshot,
      identity: current?.identity ?? snapshot.identity,
      reset_at: current?.reset_at ?? snapshot.reset_at,
    }));
  }, []);

  useEffect(() => {
    if (authLoading) return;
    void refreshUsage();
  }, [authLoading, refreshUsage, session?.user.id]);

  const value = useMemo<UsageContextValue>(
    () => ({
      usage,
      isLoading,
      error,
      refreshUsage,
      applyUsageSnapshot,
    }),
    [applyUsageSnapshot, error, isLoading, refreshUsage, usage],
  );

  return <UsageContext.Provider value={value}>{children}</UsageContext.Provider>;
};
