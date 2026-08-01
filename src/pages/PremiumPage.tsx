import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Sparkles, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getSafeAuthMessage, useAuth } from '../auth';
import { AppHeader } from '../components';
import {
  activateMockPremium,
  deactivateMockPremium,
  getMockSubscriptionStatus,
  MockSubscriptionError,
  type MockSubscriptionStatus,
} from '../services/mock-subscription-api';
import { useUsage } from '../usage';

type ModalMode = 'activate' | 'deactivate';

const comparison = [
  { feature: 'Mesečna pitanja', free: '10', premium: '200' },
  { feature: 'Preporuke iz chata', free: 'Da', premium: 'Da' },
  { feature: 'Demo Premium tok', free: 'Ne', premium: 'Da' },
];

const modalCopy = {
  activate: {
    title: 'Aktiviraj demo Premium?',
    body: 'Ovo je demonstraciona aktivacija. Kartica neće biti naplaćena i prava pretplata neće biti kreirana.',
    action: 'Aktiviraj Premium',
  },
  deactivate: {
    title: 'Vrati nalog na besplatan paket?',
    body: 'Ovo služi samo za ponovno testiranje demo toka.',
    action: 'Vrati na Free',
  },
};

const planLabel = (plan?: string | null) => (plan === 'premium' ? 'Premium' : 'Free');

const ConfirmationModal: React.FC<{
  mode: ModalMode;
  isLoading: boolean;
  onConfirm: () => void;
  onClose: () => void;
}> = ({ mode, isLoading, onConfirm, onClose }) => {
  const copy = modalCopy[mode];

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isLoading) {
        onClose();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [isLoading, onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/60 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="premium-confirm-title"
    >
      <div className="w-full max-w-sm rounded-2xl bg-hype-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="premium-confirm-title" className="text-xl font-bold leading-7 text-navy-900">
              {copy.title}
            </h2>
            <p className="mt-2 text-sm leading-6 text-navy-700">{copy.body}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            aria-label="Zatvori potvrdu"
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-hype-gray text-navy-900 transition hover:bg-hype-light disabled:cursor-not-allowed disabled:opacity-60"
          >
            <X size={18} />
          </button>
        </div>

        <div className="mt-5 grid gap-2">
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-hype-yellow px-4 py-3 text-sm font-bold text-navy-900 transition hover:bg-yellow-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading && <Loader2 size={16} className="animate-spin" />}
            {copy.action}
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className="rounded-xl bg-hype-gray px-4 py-3 text-sm font-bold text-navy-900 transition hover:bg-hype-light disabled:cursor-not-allowed disabled:opacity-60"
          >
            Odustani
          </button>
        </div>
      </div>
    </div>
  );
};

export const PremiumPage: React.FC = () => {
  const navigate = useNavigate();
  const { session, user, profile, isLoading: authLoading, refreshProfile } = useAuth();
  const { refreshUsage } = useUsage();
  const [status, setStatus] = useState<MockSubscriptionStatus | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalMode, setModalMode] = useState<ModalMode | null>(null);

  const activePlan = status?.plan ?? profile?.plan ?? 'free';
  const isEligible = Boolean(status?.enabled && status.eligible);
  const isPremium = activePlan === 'premium';

  const subtitle = useMemo(() => {
    if (!user) return 'Prijavi se da proveriš demo pristup.';
    if (isEligible && isPremium) return 'Demo Premium je aktivan na ovom nalogu.';
    if (isEligible) return 'Tvoj nalog može da aktivira demo Premium.';
    return 'Premium uskoro stiže.';
  }, [isEligible, isPremium, user]);

  useEffect(() => {
    if (authLoading) return;
    setMessage(null);
    setError(null);

    if (!session) {
      setStatus(null);
      return;
    }

    let isMounted = true;
    setIsLoadingStatus(true);
    getMockSubscriptionStatus(session)
      .then((nextStatus) => {
        if (!isMounted) return;
        setStatus(nextStatus);
      })
      .catch((requestError) => {
        if (!isMounted) return;
        setStatus(null);
        setError(
          requestError instanceof MockSubscriptionError
            ? requestError.message
            : getSafeAuthMessage(requestError),
        );
      })
      .finally(() => {
        if (isMounted) setIsLoadingStatus(false);
      });

    return () => {
      isMounted = false;
    };
  }, [authLoading, session]);

  const runMutation = async (mode: ModalMode) => {
    if (isMutating) return;
    setIsMutating(true);
    setError(null);
    setMessage(null);

    try {
      const result =
        mode === 'activate'
          ? await activateMockPremium(session)
          : await deactivateMockPremium(session);
      const nextStatus = await getMockSubscriptionStatus(session);
      setStatus(nextStatus);
      setMessage(result.message);
      setModalMode(null);
      await refreshProfile();
      await refreshUsage();
    } catch (requestError) {
      setError(
        requestError instanceof MockSubscriptionError
          ? requestError.message
          : getSafeAuthMessage(requestError),
      );
    } finally {
      setIsMutating(false);
    }
  };

  return (
    <div className="overflow-x-hidden pb-28 md:pb-6">
      <AppHeader title="Premium" />

      <main className="mx-auto w-full max-w-md px-4 py-6 md:px-6">
        <section className="rounded-2xl bg-navy-900 p-5 text-hype-white">
          <div className="flex items-start justify-between gap-3">
            <div className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-hype-yellow text-navy-900">
              <Sparkles size={21} />
            </div>
            {isEligible && isPremium && (
              <span className="rounded-full bg-hype-yellow px-3 py-1 text-xs font-bold text-navy-900">
                Demo Premium aktivan
              </span>
            )}
          </div>
          <h1 className="mt-4 text-3xl font-bold leading-tight">AskHype Premium</h1>
          <p className="mt-2 text-sm font-semibold text-hype-yellow">
            Demo — plaćanje još nije aktivirano
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-200">{subtitle}</p>
        </section>

        <section className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-hype-white">
          <div className="grid grid-cols-[1.2fr_0.7fr_0.8fr] bg-hype-gray px-4 py-3 text-xs font-bold text-navy-900">
            <span>Opcija</span>
            <span>Free</span>
            <span>Premium</span>
          </div>
          {comparison.map((row) => (
            <div
              key={row.feature}
              className="grid grid-cols-[1.2fr_0.7fr_0.8fr] border-t border-slate-100 px-4 py-3 text-sm text-navy-800"
            >
              <span className="font-semibold">{row.feature}</span>
              <span>{row.free}</span>
              <span>{row.premium}</span>
            </div>
          ))}
        </section>

        {message && (
          <p className="mt-5 rounded-2xl border border-green-200 bg-green-50 px-4 py-3 text-sm font-semibold leading-6 text-green-900">
            {message}
          </p>
        )}

        {error && (
          <p className="mt-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold leading-6 text-red-900">
            {error}
          </p>
        )}

        <section className="mt-5 rounded-2xl bg-hype-gray p-4">
          {authLoading || isLoadingStatus ? (
            <div className="flex items-center gap-2 text-sm font-semibold text-navy-700">
              <Loader2 size={16} className="animate-spin" />
              Provera demo pristupa...
            </div>
          ) : !user ? (
            <div className="space-y-3">
              <p className="text-base font-bold text-navy-900">Prijavi se da proveriš demo pristup.</p>
              <button
                type="button"
                onClick={() => navigate('/auth', { state: { redirectTo: '/premium', mode: 'signIn' } })}
                className="w-full rounded-xl bg-navy-900 px-4 py-3 text-sm font-bold text-hype-white transition hover:bg-navy-800"
              >
                Prijavi se
              </button>
            </div>
          ) : isEligible ? (
            <div className="space-y-3">
              <p className="text-sm font-semibold text-navy-700">
                Trenutni paket: <span className="text-navy-900">{planLabel(activePlan)}</span>
              </p>
              {isPremium ? (
                <button
                  type="button"
                  onClick={() => setModalMode('deactivate')}
                  className="w-full rounded-xl bg-hype-white px-4 py-3 text-sm font-bold text-navy-900 ring-1 ring-slate-200 transition hover:bg-hype-light"
                >
                  Vrati na besplatan paket
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setModalMode('activate')}
                  className="w-full rounded-xl bg-hype-yellow px-4 py-3 text-sm font-bold text-navy-900 transition hover:bg-yellow-300"
                >
                  Aktiviraj demo Premium
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-base font-bold text-navy-900">Premium uskoro stiže</p>
              <p className="text-sm leading-6 text-navy-700">
                Demo aktivacija trenutno nije dostupna za ovaj nalog.
              </p>
              <button
                type="button"
                onClick={() => setMessage('Javićemo kada Premium bude spreman za sve korisnike.')}
                className="w-full rounded-xl bg-hype-white px-4 py-3 text-sm font-bold text-navy-900 ring-1 ring-slate-200 transition hover:bg-hype-light"
              >
                Obavesti me
              </button>
            </div>
          )}
        </section>

        <button
          type="button"
          onClick={() => navigate('/chat')}
          className="mt-5 w-full rounded-xl bg-hype-gray px-4 py-3 text-sm font-bold text-navy-900 transition hover:bg-hype-light"
        >
          Nazad na Chat
        </button>
      </main>

      {modalMode && (
        <ConfirmationModal
          mode={modalMode}
          isLoading={isMutating}
          onClose={() => {
            if (!isMutating) setModalMode(null);
          }}
          onConfirm={() => void runMutation(modalMode)}
        />
      )}
    </div>
  );
};

export default PremiumPage;
