import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Loader2, Mail, UserRound } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { AskHypeLogo } from '../components';
import { getSafeAuthMessage, useAuth } from '../auth';

type AuthMode = 'signIn' | 'signUp';

type AuthLocationState = {
  redirectTo?: unknown;
  mode?: unknown;
} | null;

const isSafeRedirect = (value: unknown): value is string => {
  return (
    typeof value === 'string' &&
    value.startsWith('/') &&
    !value.startsWith('//') &&
    !value.includes('://')
  );
};

const isAuthMode = (value: unknown): value is AuthMode => value === 'signIn' || value === 'signUp';

const isValidEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

export const AuthPage: React.FC = () => {
  const navigate = useNavigate();
  const locationState = useLocation().state as AuthLocationState;
  const { user, isLoading, signIn, signUp } = useAuth();
  const redirectTo = useMemo(
    () => (isSafeRedirect(locationState?.redirectTo) ? locationState.redirectTo : '/'),
    [locationState],
  );
  const [mode, setMode] = useState<AuthMode>(isAuthMode(locationState?.mode) ? locationState.mode : 'signIn');
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirmation, setPasswordConfirmation] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && user) {
      navigate(redirectTo, { replace: true });
    }
  }, [isLoading, navigate, redirectTo, user]);

  const switchMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setError(null);
    setSuccessMessage(null);
  };

  const validate = () => {
    const trimmedEmail = email.trim();
    const trimmedName = displayName.trim();

    if (!isValidEmail(trimmedEmail)) {
      return 'Unesi validnu email adresu.';
    }
    if (password.length < 8) {
      return 'Lozinka mora imati najmanje 8 karaktera.';
    }
    if (mode === 'signUp') {
      if (!trimmedName) {
        return 'Unesi ime za nalog.';
      }
      if (password !== passwordConfirmation) {
        return 'Lozinke se ne poklapaju.';
      }
    }

    return null;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isSubmitting) return;

    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setSuccessMessage(null);

    try {
      if (mode === 'signUp') {
        const result = await signUp(email.trim(), password, displayName.trim());
        if (!result.session) {
          setSuccessMessage('Proveri email da potvrdiš nalog.');
          return;
        }
      } else {
        await signIn(email.trim(), password);
      }

      navigate(redirectTo, { replace: true });
    } catch (authError) {
      setError(getSafeAuthMessage(authError));
    } finally {
      setIsSubmitting(false);
    }
  };

  const isSignUp = mode === 'signUp';
  const submitLabel = isSignUp ? 'Napravi nalog' : 'Prijavi se';
  const isDisabled = isSubmitting || Boolean(successMessage);

  return (
    <div className="min-h-screen bg-hype-light px-4 py-6 text-navy-900">
      <main className="mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-md flex-col justify-center">
        <section className="rounded-3xl bg-hype-white p-5 shadow-sm ring-1 ring-slate-200">
          <div className="mb-6 flex items-center justify-between gap-3">
            <AskHypeLogo variant="full" />
            <button
              type="button"
              onClick={() => navigate('/', { replace: true })}
              className="inline-flex items-center gap-2 rounded-full bg-hype-gray px-3 py-2 text-xs font-bold text-navy-800 transition hover:bg-hype-yellow focus:outline-none focus:ring-2 focus:ring-navy-900 focus:ring-offset-2"
            >
              <ArrowLeft size={14} />
              Nastavi kao gost
            </button>
          </div>

          <div className="mb-5 grid grid-cols-2 gap-2 rounded-2xl bg-hype-gray p-1">
            {[
              { value: 'signIn' as const, label: 'Prijavi se' },
              { value: 'signUp' as const, label: 'Napravi nalog' },
            ].map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => switchMode(item.value)}
                className={clsx(
                  'rounded-xl px-3 py-2 text-sm font-bold transition focus:outline-none focus:ring-2 focus:ring-navy-900 focus:ring-offset-2',
                  mode === item.value
                    ? 'bg-navy-900 text-hype-white shadow-sm'
                    : 'text-navy-700 hover:bg-hype-white',
                )}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="mb-5">
            <h1 className="text-2xl font-bold">{submitLabel}</h1>
            <p className="mt-1 text-sm leading-6 text-navy-600">
              {isSignUp
                ? 'Sačuvaj profil i pripremi AskHype za personalizovane preporuke.'
                : 'Uđi u svoj AskHype nalog. Aplikaciju možeš koristiti i kao gost.'}
            </p>
          </div>

          {successMessage ? (
            <div className="rounded-2xl border border-hype-yellow bg-yellow-50 p-4">
              <div className="flex items-start gap-3">
                <Mail size={18} className="mt-1 flex-shrink-0 text-navy-900" />
                <div>
                  <p className="text-sm font-bold text-navy-900">{successMessage}</p>
                  <p className="mt-1 text-sm leading-6 text-navy-700">
                    Nakon potvrde email adrese možeš da se prijaviš ovde.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => switchMode('signIn')}
                className="mt-4 rounded-full bg-navy-900 px-4 py-2 text-sm font-bold text-hype-white"
              >
                Prijavi se
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {isSignUp && (
                <label className="block">
                  <span className="mb-2 block text-xs font-bold text-navy-700">Ime</span>
                  <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-hype-white px-3 py-2 focus-within:ring-2 focus-within:ring-navy-900">
                    <UserRound size={18} className="text-navy-500" />
                    <input
                      type="text"
                      value={displayName}
                      onChange={(event) => setDisplayName(event.target.value)}
                      disabled={isDisabled}
                      autoComplete="name"
                      className="min-h-11 flex-1 bg-transparent text-sm outline-none placeholder:text-navy-500"
                      placeholder="Tvoje ime"
                    />
                  </div>
                </label>
              )}

              <label className="block">
                <span className="mb-2 block text-xs font-bold text-navy-700">Email adresa</span>
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={isDisabled}
                  autoComplete="email"
                  className="min-h-12 w-full rounded-2xl border border-slate-200 bg-hype-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-navy-900 disabled:opacity-60"
                  placeholder="ti@example.com"
                />
              </label>

              <label className="block">
                <span className="mb-2 block text-xs font-bold text-navy-700">Lozinka</span>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  disabled={isDisabled}
                  autoComplete={isSignUp ? 'new-password' : 'current-password'}
                  className="min-h-12 w-full rounded-2xl border border-slate-200 bg-hype-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-navy-900 disabled:opacity-60"
                  placeholder="Najmanje 8 karaktera"
                />
              </label>

              {isSignUp && (
                <label className="block">
                  <span className="mb-2 block text-xs font-bold text-navy-700">Potvrdi lozinku</span>
                  <input
                    type="password"
                    value={passwordConfirmation}
                    onChange={(event) => setPasswordConfirmation(event.target.value)}
                    disabled={isDisabled}
                    autoComplete="new-password"
                    className="min-h-12 w-full rounded-2xl border border-slate-200 bg-hype-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-navy-900 disabled:opacity-60"
                    placeholder="Ponovi lozinku"
                  />
                </label>
              )}

              {error && (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-900">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={isDisabled}
                className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-navy-900 px-4 py-3 text-sm font-bold text-hype-white transition hover:bg-navy-800 focus:outline-none focus:ring-2 focus:ring-navy-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmitting && <Loader2 size={16} className="animate-spin" />}
                {submitLabel}
              </button>
            </form>
          )}

          {!successMessage && (
            <div className="mt-5 text-center text-sm text-navy-700">
              {isSignUp ? 'Već imaš nalog?' : 'Nemaš nalog?'}{' '}
              <button
                type="button"
                onClick={() => switchMode(isSignUp ? 'signIn' : 'signUp')}
                className="font-bold text-navy-900 underline decoration-hype-yellow decoration-2 underline-offset-4"
              >
                {isSignUp ? 'Prijavi se' : 'Napravi nalog'}
              </button>
            </div>
          )}
        </section>
      </main>
    </div>
  );
};

export default AuthPage;
