import { useState, type FormEvent } from 'react';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getSafeAuthMessage, useAuth } from '../auth';
import { AskHypeLogo } from '../components';
import { supabase } from '../utils/supabase';

export const ResetPasswordPage = () => {
  const navigate = useNavigate();
  const { session, isLoading, isPasswordRecovery, completePasswordRecovery } = useAuth();
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [returnError, setReturnError] = useState<string | null>(null);
  const canReset = Boolean(session && isPasswordRecovery);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (isSubmitting || !canReset) return;
    if (password.length < 8) {
      setError('Lozinka mora imati najmanje 8 karaktera.');
      return;
    }
    if (password !== confirmation) {
      setError('Lozinke se ne poklapaju.');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) throw updateError;
      setPassword('');
      setConfirmation('');
      setSuccess(true);
      completePasswordRecovery();
    } catch (authError) {
      setError(getSafeAuthMessage(authError));
    } finally {
      setIsSubmitting(false);
    }
  };

  const returnToLogin = async () => {
    setIsSubmitting(true);
    setReturnError(null);
    const { error: signOutError } = await supabase.auth.signOut({ scope: 'local' });
    if (signOutError) {
      setReturnError('Povratak na prijavu trenutno nije uspeo. Pokušajte ponovo.');
      setIsSubmitting(false);
      return;
    }
    navigate('/auth', { replace: true, state: { mode: 'signIn' } });
  };

  return (
    <div className="min-h-screen bg-hype-light px-4 py-6 text-navy-900">
      <main className="mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-md flex-col justify-center">
        <section className="rounded-3xl bg-hype-white p-5 shadow-sm ring-1 ring-slate-200">
          <div className="mb-6"><AskHypeLogo variant="full" /></div>
          <h1 className="text-2xl font-bold">Postavite novu lozinku</h1>

          {isLoading ? (
            <div className="mt-5 flex items-center gap-3 text-sm text-navy-600" role="status">
              <Loader2 size={17} className="animate-spin" /> Proveravamo link za oporavak...
            </div>
          ) : success ? (
            <div className="mt-5 rounded-2xl border border-hype-yellow bg-yellow-50 p-4">
              <div className="flex items-start gap-3">
                <CheckCircle2 size={19} className="mt-0.5 flex-none text-navy-900" />
                <div>
                  <p className="text-sm font-bold text-navy-900">Lozinka je uspešno promenjena.</p>
                  <p className="mt-1 text-sm leading-6 text-navy-700">Sada možete da se prijavite novom lozinkom.</p>
                </div>
              </div>
              {returnError && <p className="mt-3 text-sm text-red-900">{returnError}</p>}
              <button type="button" disabled={isSubmitting} onClick={() => void returnToLogin()} className="mt-4 rounded-full bg-navy-900 px-4 py-2 text-sm font-bold text-hype-white disabled:cursor-not-allowed disabled:opacity-60">
                Prijavi se
              </button>
            </div>
          ) : !canReset ? (
            <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-4">
              <p className="text-sm font-bold text-red-900">Link za promenu lozinke nije važeći ili je istekao.</p>
              <button type="button" onClick={() => navigate('/forgot-password')} className="mt-4 rounded-full bg-navy-900 px-4 py-2 text-sm font-bold text-hype-white">
                Pošalji novi link
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-5 space-y-4">
              <p className="text-sm leading-6 text-navy-600">Unesite novu lozinku od najmanje 8 karaktera.</p>
              <label className="block">
                <span className="mb-2 block text-xs font-bold text-navy-700">Nova lozinka</span>
                <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} disabled={isSubmitting} autoComplete="new-password" className="min-h-12 w-full rounded-2xl border border-slate-200 bg-hype-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-navy-900 disabled:opacity-60" />
              </label>
              <label className="block">
                <span className="mb-2 block text-xs font-bold text-navy-700">Potvrdite novu lozinku</span>
                <input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={isSubmitting} autoComplete="new-password" className="min-h-12 w-full rounded-2xl border border-slate-200 bg-hype-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-navy-900 disabled:opacity-60" />
              </label>
              {error && <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-900">{error}</div>}
              <button type="submit" disabled={isSubmitting} className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-navy-900 px-4 py-3 text-sm font-bold text-hype-white transition hover:bg-navy-800 focus:outline-none focus:ring-2 focus:ring-navy-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60">
                {isSubmitting && <Loader2 size={16} className="animate-spin" />}
                Sačuvaj novu lozinku
              </button>
            </form>
          )}
        </section>
      </main>
    </div>
  );
};

export default ResetPasswordPage;

