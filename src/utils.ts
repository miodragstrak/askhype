import type { SyntheticEvent } from 'react';
import type { UserPreferences } from './types';
import { defaultUserPreferences } from './mock-data';

// Local Storage Keys
const STORAGE_KEYS = {
  USER_PREFERENCES: 'askhype:userPreferences',
  SAVED_ITEMS: 'askhype:savedItems',
  CHAT_HISTORY: 'askhype:chatHistory',
};

export const storageUtils = {
  // User Preferences
  getUserPreferences: (): UserPreferences => {
    try {
      const stored = localStorage.getItem(STORAGE_KEYS.USER_PREFERENCES);
      return stored ? JSON.parse(stored) : defaultUserPreferences;
    } catch {
      return defaultUserPreferences;
    }
  },

  setUserPreferences: (preferences: UserPreferences): void => {
    localStorage.setItem(STORAGE_KEYS.USER_PREFERENCES, JSON.stringify(preferences));
  },

  // Saved Items
  getSavedItems: (): string[] => {
    try {
      const stored = localStorage.getItem(STORAGE_KEYS.SAVED_ITEMS);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  },

  addSavedItem: (itemId: string): void => {
    const items = storageUtils.getSavedItems();
    if (!items.includes(itemId)) {
      items.push(itemId);
      localStorage.setItem(STORAGE_KEYS.SAVED_ITEMS, JSON.stringify(items));
    }
  },

  removeSavedItem: (itemId: string): void => {
    const items = storageUtils.getSavedItems();
    const filtered = items.filter(id => id !== itemId);
    localStorage.setItem(STORAGE_KEYS.SAVED_ITEMS, JSON.stringify(filtered));
  },

  isSaved: (itemId: string): boolean => {
    return storageUtils.getSavedItems().includes(itemId);
  },

  // Chat History
  getChatHistory: () => {
    try {
      const stored = localStorage.getItem(STORAGE_KEYS.CHAT_HISTORY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  },

  saveChatMessage: (message: any): void => {
    const history = storageUtils.getChatHistory();
    history.push(message);
    localStorage.setItem(STORAGE_KEYS.CHAT_HISTORY, JSON.stringify(history));
  },

  clearChatHistory: (): void => {
    localStorage.removeItem(STORAGE_KEYS.CHAT_HISTORY);
  },
};

// Image Utils
export const imageUtils = {
  fallbackImage:
    'data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%20500%20300%22%20role%3D%22img%22%20aria-label%3D%22AskHype%22%3E%3Crect%20width%3D%22500%22%20height%3D%22300%22%20fill%3D%22%23f3f4f6%22%2F%3E%3Ccircle%20cx%3D%22250%22%20cy%3D%22122%22%20r%3D%2236%22%20fill%3D%22%23f8d84a%22%2F%3E%3Ctext%20x%3D%22250%22%20y%3D%22192%22%20font-family%3D%22Arial%2C%20sans-serif%22%20font-size%3D%2228%22%20font-weight%3D%22700%22%20text-anchor%3D%22middle%22%20fill%3D%22%23111827%22%3EAskHype%3C%2Ftext%3E%3C%2Fsvg%3E',

  // Generate a placeholder image URL
  getPlaceholder: (): string => {
    return imageUtils.fallbackImage;
  },

  getSafeSrc: (src?: string): string => {
    return src?.trim() ? src : imageUtils.fallbackImage;
  },

  // Fallback image if original fails
  onImageError: (e: SyntheticEvent<HTMLImageElement>) => {
    const image = e.currentTarget;
    if (image.src !== imageUtils.fallbackImage) {
      image.src = imageUtils.fallbackImage;
      image.alt = '';
    }
  },
};

// Date Utils
export const dateUtils = {
  formatDate: (date: string): string => {
    return new Date(date).toLocaleDateString('sr-RS', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  },

  formatTime: (date: string): string => {
    return new Date(date).toLocaleTimeString('sr-RS', {
      hour: '2-digit',
      minute: '2-digit',
    });
  },

  getRelativeTime: (date: string): string => {
    const now = new Date();
    const past = new Date(date);
    const diff = now.getTime() - past.getTime();
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (seconds < 60) return 'Upravo sada';
    if (minutes < 60) return `Pre ${minutes} min`;
    if (hours < 24) return `Pre ${hours}h`;
    if (days < 7) return `Pre ${days}d`;

    return dateUtils.formatDate(date);
  },
};

// Validation Utils
export const validationUtils = {
  isValidEmail: (email: string): boolean => {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
  },

  isValidUrl: (url: string): boolean => {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  },
};
