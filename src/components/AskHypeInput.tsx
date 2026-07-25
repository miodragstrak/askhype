import React, { useState } from 'react';
import { Send } from 'lucide-react';
import clsx from 'clsx';

interface AskHypeInputProps {
  placeholder?: string;
  onSubmit?: (value: string) => void;
  disabled?: boolean;
  className?: string;
  showSendButton?: boolean;
  variant?: 'default' | 'compact';
}

export const AskHypeInput: React.FC<AskHypeInputProps> = ({
  placeholder = 'Pitaj AskHype…',
  onSubmit,
  disabled = false,
  className,
  showSendButton = true,
  variant = 'default',
}) => {
  const [value, setValue] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim() && onSubmit) {
      onSubmit(value);
      setValue('');
    }
  };

  if (variant === 'compact') {
    return (
      <form onSubmit={handleSubmit} className={clsx('w-full', className)}>
        <div className="flex items-center gap-2 bg-hype-gray rounded-2xl px-4 py-2">
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={placeholder}
            disabled={disabled}
            className={clsx(
              'flex-1 bg-transparent outline-none text-navy-900 placeholder-navy-600',
              'text-sm',
              disabled && 'opacity-50 cursor-not-allowed'
            )}
            aria-label="Ask AskHype"
          />
          {showSendButton && (
            <button
              type="submit"
              disabled={disabled || !value.trim()}
              className={clsx(
                'p-1.5 rounded-full transition-all duration-200 flex-shrink-0',
                value.trim()
                  ? 'bg-hype-yellow text-navy-900 hover:bg-yellow-300'
                  : 'text-navy-600'
              )}
              aria-label="Send"
            >
              <Send size={18} />
            </button>
          )}
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className={clsx('w-full', className)}>
      <div className="flex items-center gap-3 bg-hype-white rounded-2xl px-4 py-3 border-2 border-navy-900">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          className={clsx(
            'flex-1 bg-transparent outline-none text-navy-900 placeholder-navy-600',
            'text-base',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
          aria-label="Ask AskHype"
        />
        {showSendButton && (
          <button
            type="submit"
            disabled={disabled || !value.trim()}
            className={clsx(
              'p-3 rounded-full transition-all duration-200 flex-shrink-0 font-semibold',
              value.trim()
                ? 'bg-hype-yellow text-navy-900 hover:bg-yellow-300 hover:scale-105'
                : 'bg-hype-gray text-navy-600 hover:bg-hype-light'
            )}
            aria-label="Send"
          >
            <Send size={20} />
          </button>
        )}
      </div>
    </form>
  );
};

export default AskHypeInput;
