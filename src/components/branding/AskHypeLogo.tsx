import React from 'react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';

type AskHypeLogoProps = {
  variant?: 'compact' | 'full';
  className?: string;
};

export const AskHypeLogo: React.FC<AskHypeLogoProps> = ({
  variant = 'compact',
  className,
}) => {
  return (
    <Link
      to="/"
      aria-label="AskHype početna"
      className={clsx(
        'inline-flex min-w-0 flex-shrink-0 items-center',
        className
      )}
    >
      <img
        src="/branding/askhype-logo.jpg"
        alt="AskHype"
        className={clsx(
          'block w-auto object-contain',
          variant === 'compact' ? 'max-h-10' : 'max-h-24'
        )}
      />
    </Link>
  );
};

export default AskHypeLogo;
