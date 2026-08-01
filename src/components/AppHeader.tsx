import React from 'react';
import { MapPin, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { AskHypeLogo } from './branding/AskHypeLogo';
import { useAuth } from '../auth';

interface AppHeaderProps {
  title?: string;
  location?: string;
  showBack?: boolean;
  onBack?: () => void;
  compact?: boolean;
}

export const AppHeader: React.FC<AppHeaderProps> = ({
  title,
  location = 'Beograd',
  showBack = false,
  onBack,
  compact = false,
}) => {
  const navigate = useNavigate();
  const { user, profile } = useAuth();
  const displayName = profile?.display_name || user?.email;
  const initials = displayName
    ? displayName
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toLocaleUpperCase('sr-RS'))
        .join('')
    : null;
  const profileLabel = user ? 'Profil naloga' : 'Prijavi se ili otvori profil';

  if (compact) {
    return (
      <header className="bg-hype-white border-b border-hype-gray sticky top-0 z-40">
        <div
          className="max-w-md mx-auto px-4 py-2 flex items-center justify-between"
          style={{ paddingTop: 'calc(0.5rem + env(safe-area-inset-top))' }}
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <AskHypeLogo variant="compact" />
            <div className="flex min-w-0 items-center gap-1 text-xs text-navy-700">
              <MapPin size={12} className="flex-shrink-0" />
              <span className="truncate">{location}</span>
            </div>
          </div>
          <button
            onClick={() => navigate('/profile')}
            className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-hype-gray transition"
            aria-label={profileLabel}
          >
            {initials ? (
              <span className="text-xs font-bold text-navy-900">{initials}</span>
            ) : (
              <User size={18} className="text-navy-900" />
            )}
          </button>
        </div>
      </header>
    );
  }

  return (
    <header className="bg-hype-white border-b border-hype-gray sticky top-0 z-40">
      <div
        className="max-w-md mx-auto px-4 py-3 flex items-center justify-between gap-2"
        style={{ paddingTop: 'calc(0.75rem + env(safe-area-inset-top))' }}
      >
        {showBack && (
          <button
            onClick={onBack}
            className="p-2 hover:bg-hype-gray rounded-lg transition flex-shrink-0"
            aria-label="Go back"
          >
            ←
          </button>
        )}
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <AskHypeLogo variant="compact" />
          <div className="min-w-0 flex-1">
            {title && (
              <h1 className="truncate text-lg font-semibold text-navy-900">{title}</h1>
            )}
            <div className="flex min-w-0 items-center gap-1 text-sm text-navy-700">
              <MapPin size={14} className="flex-shrink-0" />
              <span className="truncate">{location}</span>
            </div>
          </div>
        </div>
        {!showBack && (
          <button
            onClick={() => navigate('/profile')}
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full hover:bg-hype-gray transition"
            aria-label={profileLabel}
          >
            {initials ? (
              <span className="text-xs font-bold text-navy-900">{initials}</span>
            ) : (
              <User size={18} className="text-navy-900" />
            )}
          </button>
        )}
      </div>
    </header>
  );
};

export default AppHeader;
