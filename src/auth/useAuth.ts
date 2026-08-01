import { useContext } from 'react';
import type { AuthError } from '@supabase/supabase-js';
import { AuthContext } from './AuthContextCore';

export const useAuth = () => {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth must be used within AuthProvider.');
  }
  return value;
};

export const getSafeAuthMessage = (error: unknown) => {
  const message = ((error as AuthError | undefined)?.message ?? '').toLocaleLowerCase();

  if (message.includes('invalid login') || message.includes('invalid credentials')) {
    return 'Email ili lozinka nisu ispravni.';
  }
  if (message.includes('already registered') || message.includes('already exists')) {
    return 'Nalog sa ovom email adresom već postoji.';
  }
  if (message.includes('email not confirmed') || message.includes('not confirmed')) {
    return 'Email adresa još nije potvrđena.';
  }
  if (message.includes('password')) {
    return 'Lozinka mora biti validna i dovoljno jaka.';
  }
  if (message.includes('network') || message.includes('fetch')) {
    return 'Veza trenutno nije dostupna. Pokušaj ponovo.';
  }

  return 'Nešto nije uspelo. Proveri podatke i pokušaj ponovo.';
};
