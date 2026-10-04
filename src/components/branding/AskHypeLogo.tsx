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
      src="/branding/askhype-logo.jpg"
      alt="AskHype"
      className={clsx(
        'block object-contain',
        isConversation
          ? 'absolute left-0 top-[-106.25%] h-auto w-full'
          : ['w-auto', variant === 'compact' ? 'max-h-10' : 'max-h-24']
      )}
    />
  );

  return (
    <Link
      to="/"
      aria-label="AskHype početna"
      className={clsx(
        'inline-flex min-w-0 flex-shrink-0 items-center',
        className
      )}
    >
      {isConversation ? (
        // Window y=544..1056 of the square JPG, hiding only space around the artwork.
        <span className="relative block aspect-[3/1] w-[100px] overflow-hidden md:w-[120px]">
          {image}
        </span>
      ) : image}
    </Link>
  );
};

export default AskHypeLogo;
