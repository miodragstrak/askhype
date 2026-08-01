import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '../utils/supabase';
import { AuthContext, type AuthContextValue, type Profile } from './AuthContextCore';

const mapProfile = (value: unknown): Profile | null => {
  if (!value || typeof value !== 'object') return null;
  const row = value as Partial<Profile>;

  if (typeof row.user_id !== 'string') return null;

  return {
    user_id: row.user_id,
    display_name: row.display_name ?? null,
    plan: row.plan === 'premium' ? 'premium' : 'free',
    location: row.location ?? null,
    language: row.language ?? null,
    created_at: row.created_at ?? '',
    updated_at: row.updated_at ?? '',
  };
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(false);
  const profileRequestIdRef = useRef(0);
  const currentUserIdRef = useRef<string | null>(null);

  const loadProfile = useCallback(async (userId: string) => {
    const requestId = profileRequestIdRef.current + 1;
    profileRequestIdRef.current = requestId;
    currentUserIdRef.current = userId;
    setProfileLoading(true);

    const { data, error } = await supabase
      .from('profiles')
      .select('user_id, display_name, plan, location, language, created_at, updated_at')
      .eq('user_id', userId)
      .maybeSingle();

    if (profileRequestIdRef.current !== requestId || currentUserIdRef.current !== userId) {
      return;
    }

    setProfileLoading(false);

    if (error) {
      setProfile(null);
      return;
    }

    setProfile(mapProfile(data));
  }, []);

  const clearProfile = useCallback(() => {
    profileRequestIdRef.current += 1;
    currentUserIdRef.current = null;
    setProfile(null);
    setProfileLoading(false);
  }, []);

  const applySession = useCallback(
    (nextSession: Session | null) => {
      setSession(nextSession);
      setUser(nextSession?.user ?? null);

      if (nextSession?.user) {
        void loadProfile(nextSession.user.id);
      } else {
        clearProfile();
      }
    },
    [clearProfile, loadProfile],
  );

  useEffect(() => {
    let isMounted = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!isMounted) return;
      applySession(data.session);
      setIsLoading(false);
    });

    const { data } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (
        event === 'INITIAL_SESSION' ||
        event === 'SIGNED_IN' ||
        event === 'SIGNED_OUT' ||
        event === 'TOKEN_REFRESHED' ||
        event === 'USER_UPDATED'
      ) {
        applySession(nextSession);
        setIsLoading(false);
      }
    });

    return () => {
      isMounted = false;
      data.subscription.unsubscribe();
    };
  }, [applySession]);

  const signUp = useCallback(
    async (email: string, password: string, displayName: string) => {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            display_name: displayName,
            language: 'sr',
          },
        },
      });

      if (error) throw error;
      if (data.session) {
        applySession(data.session);
      }
      return { session: data.session };
    },
    [applySession],
  );

  const signIn = useCallback(
    async (email: string, password: string) => {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
      applySession(data.session);
    },
    [applySession],
  );

  const signOut = useCallback(async () => {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
    applySession(null);
  }, [applySession]);

  const refreshProfile = useCallback(async () => {
    if (!user) {
      clearProfile();
      return;
    }
    await loadProfile(user.id);
  }, [clearProfile, loadProfile, user]);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user,
      profile,
      isLoading,
      profileLoading,
      signUp,
      signIn,
      signOut,
      refreshProfile,
    }),
    [isLoading, profile, profileLoading, refreshProfile, session, signIn, signOut, signUp, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
