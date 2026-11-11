import React from 'react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';

type AskHypeLogoProps = {
  variant?: 'compact' | 'full' | 'conversation';
  className?: string;
};

export const AskHypeLogo: React.FC<AskHypeLogoProps> = ({
  variant = 'compact',
  className,
}) => {
  const isConversation = variant === 'conversation';
  const image = (
    <img
      src="/branding/askhype-logo.png"
      alt="AskHype"
      className={clsx(
        'block h-auto max-w-full object-contain',
        isConversation
          ? 'w-[112px] sm:w-[128px] md:w-[140px]'
          : ['w-auto', variant === 'compact' ? 'max-h-10' : 'max-h-24']
      )}
    />
  );

  return (
    <Link
      to="/"
      aria-label="AskHype početna"
      className={clsx(
        'inline-flex min-w-0 flex-shrink-0 items-center rounded-[4px] bg-[var(--app-logo-backing)] px-1 py-0.5',
        className
      )}
    >
      {image}
    </Link>
  );
};

export default AskHypeLogo;
