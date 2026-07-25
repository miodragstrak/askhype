import React from 'react';
import { X } from 'lucide-react';
import clsx from 'clsx';

interface FilterChipProps {
  label: string;
  onRemove?: () => void;
  onClick?: () => void;
  selected?: boolean;
  removable?: boolean;
  className?: string;
  variant?: 'default' | 'active';
}

export const FilterChip: React.FC<FilterChipProps> = ({
  label,
  onRemove,
  onClick,
  selected = false,
  removable = false,
  className,
  variant = 'default',
}) => {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'px-4 py-2 rounded-full transition-all duration-200 flex items-center gap-2',
        'whitespace-nowrap text-sm font-medium',
        variant === 'active' || selected
          ? 'bg-navy-900 text-hype-white'
          : 'bg-hype-gray text-navy-700 hover:bg-hype-light',
        className
      )}
    >
      <span>{label}</span>
      {removable && onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="p-0 hover:bg-opacity-20 rounded-full transition-colors"
          aria-label={`Remove ${label} filter`}
        >
          <X size={16} />
        </button>
      )}
    </button>
  );
};

export default FilterChip;
