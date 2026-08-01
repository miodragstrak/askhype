import React, { useState } from 'react';
import { Check, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { AppHeader } from '../components';

const premiumBenefits = [
  'Do 200 AskHype pitanja mesečno',
  'Više prostora za planiranje putovanja, događaja i izlazaka',
  'Pristup budućim premium preporukama čim budu spremne',
];

export const PremiumPage: React.FC = () => {
  const navigate = useNavigate();
  const [showNotice, setShowNotice] = useState(false);

  return (
    <div className="overflow-x-hidden pb-28 md:pb-6">
      <AppHeader title="Premium" />

      <main className="mx-auto w-full max-w-md px-4 py-6 md:px-6">
        <section className="rounded-2xl bg-navy-900 p-5 text-hype-white">
          <div className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-hype-yellow text-navy-900">
            <Sparkles size={21} />
          </div>
          <h1 className="mt-4 text-3xl font-bold leading-tight">AskHype Premium</h1>
          <p className="mt-2 text-sm leading-6 text-slate-200">
            Mock paket za testiranje toka nadogradnje. Plaćanje još nije povezano.
          </p>
        </section>

        <section className="mt-5 space-y-3 rounded-2xl bg-hype-gray p-4">
          {premiumBenefits.map((benefit) => (
            <div key={benefit} className="flex items-start gap-3 text-sm font-semibold text-navy-800">
              <span className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-hype-yellow text-navy-900">
                <Check size={14} />
              </span>
              <span className="leading-6">{benefit}</span>
            </div>
          ))}
        </section>

        {showNotice && (
          <p className="mt-5 rounded-2xl border border-hype-yellow bg-yellow-50 px-4 py-3 text-sm font-semibold leading-6 text-navy-900">
            Premium tok je spreman za UI proveru. Stvarna kupovina se povezuje u sledećem koraku.
          </p>
        )}

        <div className="mt-5 grid gap-3">
          <button
            type="button"
            onClick={() => setShowNotice(true)}
            className="rounded-xl bg-hype-yellow px-4 py-3 text-sm font-bold text-navy-900 transition hover:bg-yellow-300"
          >
            Aktiviraj Premium
          </button>
          <button
            type="button"
            onClick={() => navigate('/chat')}
            className="rounded-xl bg-hype-gray px-4 py-3 text-sm font-bold text-navy-900 transition hover:bg-hype-light"
          >
            Nazad na Chat
          </button>
        </div>
      </main>
    </div>
  );
};

export default PremiumPage;
