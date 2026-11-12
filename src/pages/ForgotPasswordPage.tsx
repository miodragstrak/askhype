import { useState, type FormEvent } from 'react';
import { ArrowLeft, Loader2, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import { AskHypeLogo } from '../components';
import { supabase } from '../utils/supabase';

const isValidEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

const isRecoveryRateLimitError = (error: unknown) => {
  if (!error || typeof error !== 'object') return false;
  const authError = error as { status?: unknown; code?: unknown };
  return (
    authError.status === 429 ||
    authError.code === 'over_request_rate_limit' ||
    authError.code === 'over_email_send_rate_limit'
  );
};

export const ForgotPasswordPage = () => {
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (isSubmitting) return;
    if (!isValidEmail(email.trim())) {
      setError('Unesi validnu email adresu.');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (resetError) throw resetError;
      setSuccess(true);
    } catch (resetError) {
      setError(
        isRecoveryRateLimitError(resetError)
          ? 'Previše zahteva za slanje emaila. Pokušajte ponovo malo kasnije.'
          : 'Slanje linka trenutno nije uspelo. Pokušaj ponovo kasnije.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-hype-light px-4 py-6 text-navy-900">
      <main className="mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-md flex-col justify-center">
        <section className="rounded-3xl bg-hype-white p-5 shadow-sm ring-1 ring-slate-200">
          <div className="mb-6 flex items-center justify-between gap-3">
            <AskHypeLogo variant="compact" />
            <Link to="/auth" className="inline-flex items-center gap-2 rounded-full bg-hype-gray px-3 py-2 text-xs font-bold text-navy-800 transition hover:bg-hype-yellow focus:outline-none focus:ring-2 focus:ring-navy-900">
              <ArrowLeft size={14} /> Prijava
            </Link>
          </div>

          <h1 className="text-2xl font-bold">Zaboravljena lozinka</h1>
          <p className="mt-2 text-sm leading-6 text-navy-600">
            Unesite email adresu i poslaćemo vam link za postavljanje nove lozinke.
          </p>

          {success ? (
            <div className="mt-5 rounded-2xl border border-hype-yellow bg-yellow-50 p-4">
              <div className="flex items-start gap-3">
                <Mail size={18} className="mt-1 flex-none text-navy-900" />
                <p className="text-sm font-bold leading-6 text-navy-900">
                  Ako postoji nalog sa ovom email adresom, poslali smo link za promenu lozinke.
                </p>
              </div>
              <Link to="/auth" className="mt-4 inline-flex rounded-full bg-navy-900 px-4 py-2 text-sm font-bold text-hype-white">
                Nazad na prijavu
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-5 space-y-4">
              <label className="block">
                <span className="mb-2 block text-xs font-bold text-navy-700">Email adresa</span>
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={isSubmitting}
                  autoComplete="email"
                  className="min-h-12 w-full rounded-2xl border border-slate-200 bg-hype-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-navy-900 disabled:opacity-60"
                  placeholder="ti@example.com"
                />
              </label>
              {error && <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-900">{error}</div>}
              <button type="submit" disabled={isSubmitting} className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-navy-900 px-4 py-3 text-sm font-bold text-hype-white transition hover:bg-navy-800 focus:outline-none focus:ring-2 focus:ring-navy-900 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60">
                {isSubmitting && <Loader2 size={16} className="animate-spin" />}
                Pošalji link
              </button>
            </form>
          )}
        </section>
      </main>
    </div>
  );
};

export default ForgotPasswordPage;

