import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../theme/theme-context';

interface ThemeToggleProps {
  conversation?: boolean;
}

export const ThemeToggle = ({ conversation = false }: ThemeToggleProps) => {
  const { theme, toggleTheme } = useTheme();
  const nextTheme = theme === 'dark' ? 'svetlu' : 'tamnu';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Uključi ${nextTheme} temu`}
      title={`Uključi ${nextTheme} temu`}
      className={
        conversation
          ? 'inline-flex h-10 w-10 items-center justify-center rounded-full text-chat-muted transition hover:bg-chat-hover hover:text-chat-text focus:outline-none focus:ring-2 focus:ring-hype-yellow'
          : 'inline-flex h-9 w-9 items-center justify-center rounded-full text-navy-700 transition hover:bg-hype-gray hover:text-navy-900 focus:outline-none focus:ring-2 focus:ring-focus-ring'
      }
    >
      {theme === 'dark' ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
    </button>
  );
};

