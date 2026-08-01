import React, { useState } from 'react';
import { Loader2, LogOut, UserRound } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { AppHeader } from '../components';
import { locations, categories } from '../mock-data';
import { storageUtils } from '../utils';
import type { UserPreferences } from '../types';
import { srLabels } from '../constants/labels';
import { getSafeAuthMessage, useAuth } from '../auth';

const planLabel = (plan?: string | null) => {
  if (plan === 'premium') return 'Premium';
  return 'Besplatan paket';
};

const initialsFrom = (value?: string | null) => {
  const parts = value?.trim().split(/\s+/).filter(Boolean) ?? [];
  if (!parts.length) return 'AH';
  return parts.slice(0, 2).map((part) => part[0]?.toLocaleUpperCase('sr-RS')).join('');
};

export const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const { user, profile, isLoading, profileLoading, signOut } = useAuth();
  const [preferences, setPreferences] = useState<UserPreferences>(storageUtils.getUserPreferences());
  const [hasChanges, setHasChanges] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const categoryArray = Object.values(categories);
  const displayName = profile?.display_name || user?.email || 'AskHype korisnik';

  const handleSignOut = async () => {
    if (isSigningOut) return;

    setIsSigningOut(true);
    setAuthError(null);
    try {
      await signOut();
    } catch (error) {
      setAuthError(getSafeAuthMessage(error));
    } finally {
      setIsSigningOut(false);
    }
  };

  const handleCityChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newPrefs = { ...preferences, city: e.target.value };
    setPreferences(newPrefs);
    setHasChanges(true);
  };

  const handleLanguageChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newPrefs = { ...preferences, language: e.target.value };
    setPreferences(newPrefs);
    setHasChanges(true);
  };

  const handleCurrencyChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newPrefs = { ...preferences, currency: e.target.value };
    setPreferences(newPrefs);
    setHasChanges(true);
  };

  const handleInterestToggle = (categoryId: string) => {
    const newInterests = preferences.interests.includes(categoryId)
      ? preferences.interests.filter((id) => id !== categoryId)
      : [...preferences.interests, categoryId];
    const newPrefs = { ...preferences, interests: newInterests };
    setPreferences(newPrefs);
    setHasChanges(true);
  };

  const handleRecommendationStyleChange = (style: 'adventurous' | 'relaxed' | 'cultural' | 'balanced') => {
    const newPrefs = { ...preferences, recommendationStyle: style };
    setPreferences(newPrefs);
    setHasChanges(true);
  };

  const handleSave = () => {
    storageUtils.setUserPreferences(preferences);
    setHasChanges(false);
    alert('Preferencije su sačuvane!');
  };

  const cityOptions = Object.values(locations);
  const uniqueCountries = Array.from(new Set(cityOptions.map((l) => l.country)));

  return (
    <div className="pb-28 md:pb-6 overflow-x-hidden">
      <AppHeader title="Profil" />

      <main className="max-w-md mx-auto px-4 py-6 space-y-6">
        <section className="rounded-2xl bg-hype-gray p-4">
          {isLoading ? (
            <div className="flex items-center gap-3 text-sm font-semibold text-navy-700">
              <Loader2 size={16} className="animate-spin" />
              Učitavanje naloga...
            </div>
          ) : user ? (
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-navy-900 text-sm font-bold text-hype-yellow">
                  {initialsFrom(profile?.display_name || user.email)}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="break-words text-base font-bold text-navy-900">{displayName}</p>
                  {user.email && (
                    <p className="break-words text-sm text-navy-600">{user.email}</p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold text-navy-700">
                    <span className="rounded-full bg-hype-yellow px-3 py-1 text-navy-900">
                      {profileLoading ? 'Učitavanje paketa...' : planLabel(profile?.plan)}
                    </span>
                    {(profile?.location || preferences.city) && (
                      <span className="rounded-full bg-hype-white px-3 py-1">
                        {profile?.location || preferences.city}
                      </span>
                    )}
                    {(profile?.language || preferences.language) && (
                      <span className="rounded-full bg-hype-white px-3 py-1">
                        {profile?.language || preferences.language}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              {authError && (
                <p className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
                  {authError}
                </p>
              )}
              <button
                type="button"
                onClick={handleSignOut}
                disabled={isSigningOut}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-navy-900 px-4 py-3 text-sm font-bold text-hype-white transition hover:bg-navy-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSigningOut ? <Loader2 size={16} className="animate-spin" /> : <LogOut size={16} />}
                Odjavi se
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-hype-white text-navy-900">
                  <UserRound size={22} />
                </div>
                <div>
                  <p className="text-base font-bold text-navy-900">Koristiš AskHype kao gost.</p>
                  <p className="mt-1 text-sm leading-6 text-navy-700">
                    Možeš da nastaviš bez naloga. Prijava čuva profil za sledeće korake.
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => navigate('/auth', { state: { redirectTo: '/profile', mode: 'signIn' } })}
                  className="rounded-xl bg-navy-900 px-4 py-3 text-sm font-bold text-hype-white"
                >
                  Prijavi se
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/auth', { state: { redirectTo: '/profile', mode: 'signUp' } })}
                  className="rounded-xl bg-hype-yellow px-4 py-3 text-sm font-bold text-navy-900"
                >
                  Napravi nalog
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Location Settings */}
        <section>
          <h2 className="text-sm font-bold text-navy-900 mb-4">Lokacija i Jezici</h2>
          <div className="space-y-4 bg-hype-gray rounded-2xl p-4">
            {/* City */}
            <div>
              <label className="block text-xs font-semibold text-navy-700 mb-2">
                Grad
              </label>
              <select
                value={preferences.city}
                onChange={handleCityChange}
                className="w-full px-3 py-2 border border-navy-200 rounded-lg text-sm bg-hype-white text-navy-900 focus:outline-none focus:ring-2 focus:ring-navy-900"
              >
                {cityOptions.map((city) => (
                  <option key={city.id} value={city.name}>
                    {city.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Country */}
            <div>
              <label className="block text-xs font-semibold text-navy-700 mb-2">
                Država
              </label>
              <select
                value={preferences.country}
                onChange={(e) => {
                  const newPrefs = { ...preferences, country: e.target.value };
                  setPreferences(newPrefs);
                  setHasChanges(true);
                }}
                className="w-full px-3 py-2 border border-navy-200 rounded-lg text-sm bg-hype-white text-navy-900 focus:outline-none focus:ring-2 focus:ring-navy-900"
              >
                {uniqueCountries.map((country) => (
                  <option key={country} value={country}>
                    {country}
                  </option>
                ))}
              </select>
            </div>

            {/* Language */}
            <div>
              <label className="block text-xs font-semibold text-navy-700 mb-2">
                Jezik
              </label>
              <select
                value={preferences.language}
                onChange={handleLanguageChange}
                className="w-full px-3 py-2 border border-navy-200 rounded-lg text-sm bg-hype-white text-navy-900 focus:outline-none focus:ring-2 focus:ring-navy-900"
              >
                <option value="sr">Srpski</option>
                <option value="en">English</option>
                <option value="hr">Hrvatski</option>
                <option value="de">Deutsch</option>
              </select>
            </div>

            {/* Currency */}
            <div>
              <label className="block text-xs font-semibold text-navy-700 mb-2">
                Valuta
              </label>
              <select
                value={preferences.currency}
                onChange={handleCurrencyChange}
                className="w-full px-3 py-2 border border-navy-200 rounded-lg text-sm bg-hype-white text-navy-900 focus:outline-none focus:ring-2 focus:ring-navy-900"
              >
                <option value="RSD">RSD - Srpski dinar</option>
                <option value="EUR">EUR - Evro</option>
                <option value="HRK">HRK - Hrvaćka kuna</option>
                <option value="USD">USD - Američki dolar</option>
              </select>
            </div>
          </div>
        </section>

        {/* Interests */}
        <section>
          <h2 className="text-sm font-bold text-navy-900 mb-4">Tvoji interesi</h2>
          <div className="grid grid-cols-2 gap-3">
            {categoryArray.map((category) => (
              <button
                key={category.id}
                onClick={() => handleInterestToggle(category.id)}
                className={`p-3 rounded-lg transition-all text-sm font-medium ${
                  preferences.interests.includes(category.id)
                    ? 'bg-navy-900 text-hype-white'
                    : 'bg-hype-gray text-navy-700 hover:bg-hype-light'
                }`}
              >
                {category.name}
              </button>
            ))}
          </div>
        </section>

        {/* Recommendation Style */}
        <section>
          <h2 className="text-sm font-bold text-navy-900 mb-4">Stil preporuka</h2>
          <div className="space-y-2 bg-hype-gray rounded-2xl p-4">
            {[
              { value: 'adventurous' as const, label: 'Avanturističko', desc: 'Riskantni i nov sadržaj' },
              { value: 'relaxed' as const, label: 'Opušteno', desc: 'Mirni i bezbedan izbor' },
              { value: 'cultural' as const, label: 'Kulturno', desc: 'Istorija i tradicija' },
              { value: 'balanced' as const, label: 'Balansirano', desc: 'Sve malo' },
            ].map((style) => (
              <button
                key={style.value}
                onClick={() => handleRecommendationStyleChange(style.value)}
                className={`w-full text-left p-3 rounded-lg transition-all ${
                  preferences.recommendationStyle === style.value
                    ? 'bg-navy-900 text-hype-white'
                    : 'bg-hype-white text-navy-700 hover:bg-hype-light border border-hype-gray'
                }`}
              >
                <div className="font-medium text-sm">{style.label}</div>
                <div className={`text-xs ${preferences.recommendationStyle === style.value ? 'text-hype-light' : 'text-navy-600'}`}>
                  {style.desc}
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* Privacy & History Section (Placeholder) */}
        <section>
          <h2 className="text-sm font-bold text-navy-900 mb-4">Privatnost i istorija</h2>
          <div className="space-y-3 bg-hype-gray rounded-2xl p-4">
            <button className="w-full text-left text-sm text-navy-700 hover:text-navy-900 py-2 px-2 hover:bg-hype-light rounded transition">
              Pregled istorije pretraga
            </button>
            <button className="w-full text-left text-sm text-navy-700 hover:text-navy-900 py-2 px-2 hover:bg-hype-light rounded transition">
              Upravljaj lokacijom
            </button>
            <button className="w-full text-left text-sm text-navy-700 hover:text-navy-900 py-2 px-2 hover:bg-hype-light rounded transition">
              Politika privatnosti
            </button>
            <button className="w-full text-left text-sm text-navy-700 hover:text-navy-900 py-2 px-2 hover:bg-hype-light rounded transition">
              O AskHype
            </button>
          </div>
        </section>

        {/* Save Button */}
        {hasChanges && (
          <button
            onClick={handleSave}
            className="w-full py-3 bg-navy-900 text-hype-white rounded-lg font-semibold text-sm hover:bg-navy-800 transition-colors"
          >
            {srLabels.savePreferences}
          </button>
        )}
      </main>
    </div>
  );
};

export default ProfilePage;
