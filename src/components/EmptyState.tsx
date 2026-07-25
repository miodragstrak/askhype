import React from 'react';
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className,
}) => {
  return (
    <div className={`text-center py-12 px-6 ${className}`}>
      <div className="flex justify-center mb-4">
        {icon || <Inbox size={48} className="text-navy-600" />}
      </div>
      <h3 className="text-lg font-bold text-navy-900 mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-navy-600 mb-6">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="px-6 py-2 bg-navy-900 text-hype-white rounded-full font-medium text-sm hover:bg-navy-800 transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
};

export default EmptyState;
