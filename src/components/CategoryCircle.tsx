import React from 'react';
import * as Icons from 'lucide-react';
import clsx from 'clsx';

interface CategoryCircleProps {
  name: string;
  iconName: string;
  color: string;
  onClick?: () => void;
  selected?: boolean;
  className?: string;
}

export const CategoryCircle: React.FC<CategoryCircleProps> = ({
  name,
  iconName,
  color,
  onClick,
  selected = false,
  className,
}) => {
  const IconComponent = (Icons as any)[iconName] || Icons.Zap;

  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex flex-col items-center gap-2 transition-all duration-200',
        className
      )}
    >
      <div
        className={clsx(
          'w-16 h-16 rounded-full flex items-center justify-center',
          'transition-all duration-200',
          selected ? 'ring-2 ring-offset-2 ring-navy-900 scale-110' : 'hover:scale-105'
        )}
        style={{ backgroundColor: `${color}20`, color: color }}
      >
        <IconComponent size={28} />
      </div>
      <span className="text-xs font-medium text-navy-900 text-center line-clamp-2">
        {name}
      </span>
    </button>
  );
};

export default CategoryCircle;
