import React from 'react';
import * as Icons from 'lucide-react';
import clsx from 'clsx';

interface QuickPromptChipProps {
  text: string;
  iconName: string;
  onClick?: () => void;
  variant?: 'default' | 'outline';
  className?: string;
}

export const QuickPromptChip: React.FC<QuickPromptChipProps> = ({
  text,
  iconName,
  onClick,
  variant = 'outline',
  className,
}) => {
  // Get icon from lucide-react dynamically
  const IconComponent = (Icons as any)[iconName] || Icons.Zap;

  return (
    <button
      onClick={onClick}
      className={clsx(
        'px-4 py-3 rounded-full transition-all duration-200',
        'flex items-center gap-2 text-sm font-medium',
        'min-w-max whitespace-nowrap',
        variant === 'outline'
          ? 'border-2 border-navy-900 text-navy-900 hover:bg-navy-900 hover:text-hype-white'
          : 'bg-navy-900 text-hype-white hover:bg-navy-800',
        className
      )}
    >
      <IconComponent size={16} />
      <span>{text}</span>
    </button>
  );
};

export default QuickPromptChip;
