import { createContext } from 'react';
import type { UsageSnapshot } from '../services/chat-api';

export interface UsageContextValue {
  usage: UsageSnapshot | null;
  isLoading: boolean;
  error: string | null;
  refreshUsage: () => Promise<void>;
  applyUsageSnapshot: (snapshot: UsageSnapshot | null) => void;
}

export const UsageContext = createContext<UsageContextValue | undefined>(undefined);
