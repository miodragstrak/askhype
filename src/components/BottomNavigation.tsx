import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Home, Compass, Heart, User, MessageCircle } from 'lucide-react';
import clsx from 'clsx';
import { srLabels } from '../constants/labels';

export const BottomNavigation: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const isActive = (path: string) => location.pathname === path;

  const navItems = [
    { path: '/', label: 'Početna', icon: Home },
    null, // Placeholder for center button
    { path: '/explore', label: 'Istraži', icon: Compass },
    { path: '/saved', label: srLabels.saved, icon: Heart },
    { path: '/profile', label: 'Profil', icon: User },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-hype-white border-t border-hype-gray md:hidden z-50">
      <div
        className="max-w-md mx-auto px-0"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="flex items-center justify-between relative">
          {navItems.map((item) => {
            if (item === null) {
              return (
                <div key="center-btn" className="flex-1 flex justify-center -translate-y-6">
                  <button
                    onClick={() => navigate('/chat')}
                    className={clsx(
                      'w-16 h-16 rounded-full flex items-center justify-center',
                      'transition-all duration-200 shadow-lg hover:shadow-xl',
                      'font-semibold text-lg',
                      isActive('/chat')
                        ? 'bg-hype-yellow text-navy-900 scale-105'
                        : 'bg-hype-yellow text-navy-900 hover:scale-105'
                    )}
                    aria-label="Pitaj"
                    title="Pitaj AskHype"
                  >
                    <MessageCircle size={24} />
                  </button>
                </div>
              );
            }

            const Icon = item.icon;
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={clsx(
                  'flex-1 flex flex-col items-center justify-center py-3 px-2',
                  'transition-colors duration-200 relative text-center',
                  isActive(item.path)
                    ? 'text-navy-900'
                    : 'text-navy-600 hover:text-navy-700'
                )}
                aria-label={item.label}
                aria-current={isActive(item.path) ? 'page' : undefined}
              >
                <Icon
                  size={22}
                  className={isActive(item.path) ? 'fill-current' : ''}
                />
                <span className="text-xs mt-1 font-semibold whitespace-nowrap">{item.label}</span>
                {isActive(item.path) && (
                  <div className="absolute bottom-0 w-full h-1 bg-navy-900 rounded-t" />
                )}
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
};

export default BottomNavigation;
