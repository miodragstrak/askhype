import { useContext } from 'react';
import { UsageContext } from './UsageContextCore';

export const useUsage = () => {
  const context = useContext(UsageContext);
  if (!context) {
    throw new Error('useUsage must be used within a UsageProvider.');
  }

  return context;
};
