import React, { useState } from 'react';
import { Heart, Share2, Clock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { imageUtils, storageUtils } from '../utils';
import { srLabels } from '../constants/labels';

interface HypeContentCardProps {
  id: string;
  title: string;
  excerpt: string;
  imageUrl: string;
  author: string;
  readTime: number;
  category?: string;
  isSaved?: boolean;
  onSaveChange?: (saved: boolean) => void;
  className?: string;
}

export const HypeContentCard: React.FC<HypeContentCardProps> = ({
  id,
  title,
  excerpt,
  imageUrl,
  author,
  readTime,
  category,
  isSaved: initialSaved = false,
  onSaveChange,
  className,
}) => {
  const navigate = useNavigate();
  const [isSaved, setIsSaved] = useState(initialSaved || storageUtils.isSaved(id));

  const handleSaveToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    const newSaved = !isSaved;
    setIsSaved(newSaved);

    if (newSaved) {
      storageUtils.addSavedItem(id);
    } else {
      storageUtils.removeSavedItem(id);
    }

    onSaveChange?.(newSaved);
  };

  const handleShare = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (navigator.share) {
      navigator.share({
        title: title,
        text: excerpt,
      });
    }
  };

  const handleClick = () => {
    navigate(`/recommendations/${id}`);
  };

  return (
    <article
      onClick={handleClick}
      className={clsx(
        'bg-hype-white rounded-3xl overflow-hidden shadow-sm hover:shadow-md',
        'transition-all duration-200 cursor-pointer',
        className
      )}
    >
      {/* Image */}
      <div className="relative w-full overflow-hidden bg-hype-gray" style={{ aspectRatio: '16/9' }}>
        <img
          src={imageUtils.getSafeSrc(imageUrl)}
          alt={title}
          onError={imageUtils.onImageError}
          className="w-full h-full object-cover"
          loading="lazy"
        />
        {category && (
          <div className="absolute top-2 left-2 bg-hype-yellow text-navy-900 px-3 py-1 rounded-full text-xs font-semibold">
            {category}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        <h3 className="font-bold text-navy-900 text-sm line-clamp-2 mb-2">
          {title}
        </h3>

        <p className="text-xs text-navy-600 line-clamp-2 mb-3">
          {excerpt}
        </p>

        {/* Meta Info */}
        <div className="flex items-center justify-between text-xs text-navy-700 mb-3">
          <span className="font-medium">{author}</span>
          <div className="flex items-center gap-1">
            <Clock size={14} />
            <span>{readTime} min</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <button
            onClick={handleSaveToggle}
            className={clsx(
              'flex-1 py-2 rounded-lg transition-all duration-200 flex items-center justify-center gap-1',
              isSaved
                ? 'bg-hype-yellow text-navy-900'
                : 'bg-hype-gray text-navy-600 hover:bg-hype-light'
            )}
          >
            <Heart size={16} className={isSaved ? 'fill-current' : ''} />
            <span className="text-xs font-medium">
              {isSaved ? srLabels.saved : srLabels.save}
            </span>
          </button>
          <button
            onClick={handleShare}
            className="flex-1 py-2 rounded-lg bg-hype-gray text-navy-600 hover:bg-hype-light transition-all duration-200 flex items-center justify-center gap-1"
          >
            <Share2 size={16} />
            <span className="text-xs font-medium">Deli</span>
          </button>
        </div>
      </div>
    </article>
  );
};

export default HypeContentCard;
