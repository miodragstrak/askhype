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
        'block object-contain',
        isConversation
          ? 'absolute left-0 top-[-26.92%] h-auto w-full'
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
        // Window y=175..825 of the square PNG keeps all artwork and the tagline.
        <span className="relative block aspect-[20/13] w-[80px] overflow-hidden md:w-[84px]">
          {image}
        </span>
      ) : image}
    </Link>
  );
};

export default AskHypeLogo;
