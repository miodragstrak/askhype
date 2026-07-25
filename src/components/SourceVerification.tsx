import React from 'react';
import { CheckCircle, Clock } from 'lucide-react';
import { dateUtils } from '../utils';

interface SourceVerificationProps {
  verified: boolean;
  lastVerified?: string;
  source?: string;
  className?: string;
}

export const SourceVerification: React.FC<SourceVerificationProps> = ({
  verified,
  lastVerified,
  source = 'AskHype',
  className,
}) => {
  return (
    <div className={`bg-hype-gray rounded-lg p-3 ${className}`}>
      <div className="flex items-start gap-2">
        {verified ? (
          <CheckCircle size={16} className="text-green-600 flex-shrink-0 mt-0.5" />
        ) : (
          <Clock size={16} className="text-yellow-600 flex-shrink-0 mt-0.5" />
        )}
        <div className="flex-1 text-xs text-navy-700">
          <p className="font-medium mb-1">
            {verified ? 'Verifikovano' : 'Čekanje verifikacije'}
          </p>
          <p>Izvor: {source}</p>
          {lastVerified && (
            <p className="text-navy-600 mt-1">
              Poslednja provera: {dateUtils.getRelativeTime(lastVerified)}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default SourceVerification;
