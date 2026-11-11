import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { ThemeContext, type Theme, type ThemeContextValue } from './theme-context';

const THEME_STORAGE_KEY = 'askhype:theme:v1';

const systemTheme = (): Theme =>
  window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

const initialTheme = (): Theme => {
  const documentTheme = document.documentElement.dataset.theme;
  return documentTheme === 'dark' || documentTheme === 'light' ? documentTheme : systemTheme();
};

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    themeColor?.setAttribute('content', theme === 'dark' ? '#0B1220' : '#FFFFFF');
  }, [theme]);

  useEffect(() => {
    if (localStorage.getItem(THEME_STORAGE_KEY)) return;

    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const updateFromSystem = (event: MediaQueryListEvent) => setTheme(event.matches ? 'dark' : 'light');
    media.addEventListener('change', updateFromSystem);
    return () => media.removeEventListener('change', updateFromSystem);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      toggleTheme: () => {
        setTheme((current) => {
          const next = current === 'dark' ? 'light' : 'dark';
          localStorage.setItem(THEME_STORAGE_KEY, next);
          return next;
        });
      },
    }),
    [theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

