import { createContext } from 'react';
import type { Session, User } from '@supabase/supabase-js';

export type ProfilePlan = 'free' | 'premium';

export interface Profile {
  user_id: string;
  display_name: string | null;
  plan: ProfilePlan;
  location: string | null;
  language: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuthContextValue {
  session: Session | null;
  user: User | null;
  profile: Profile | null;
  isLoading: boolean;
  profileLoading: boolean;
  signUp: (email: string, password: string, displayName: string) => Promise<{ session: Session | null }>;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
