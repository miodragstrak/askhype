import React, { useState } from 'react';
import { Heart, Share2, MapPin, Star } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { imageUtils, storageUtils } from '../utils';
import { srLabels } from '../constants/labels';

interface RecommendationCardProps {
  id: string;
  title: string;
  description: string;
  imageUrl: string;
  location?: string;
  rating?: number;
  category?: string;
  price?: number;
  isSaved?: boolean;
  onSaveChange?: (saved: boolean) => void;
  className?: string;
}

export const RecommendationCard: React.FC<RecommendationCardProps> = ({
  id,
  title,
  description,
  imageUrl,
  location,
  rating,
  category,
  price,
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
        text: description,
      });
    }
  };

  const handleClick = () => {
    navigate(`/recommendations/${id}`);
  };

  return (
    <div
      onClick={handleClick}
      className={clsx(
        'bg-hype-white rounded-3xl overflow-hidden shadow-sm hover:shadow-md',
        'transition-all duration-200 cursor-pointer',
        'flex flex-col h-full',
        className
      )}
    >
      {/* Image */}
      <div className="relative w-full bg-hype-gray overflow-hidden" style={{ aspectRatio: '16/10' }}>
        <img
          src={imageUtils.getSafeSrc(imageUrl)}
          alt={title}
          onError={imageUtils.onImageError}
          className="w-full h-full object-cover"
          loading="lazy"
        />
        {price && (
          <div className="absolute top-2 right-2 bg-navy-900 text-hype-white px-3 py-1 rounded-full text-xs font-bold">
            {price} RSD
          </div>
        )}
        {category && (
          <div className="absolute top-2 left-2 bg-hype-yellow text-navy-900 px-3 py-1 rounded-full text-xs font-bold">
            {category}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 p-3 flex flex-col">
        <h3 className="font-bold text-navy-900 text-sm line-clamp-2 mb-2">
          {title}
        </h3>

        <p className="text-xs text-navy-600 line-clamp-2 mb-3 flex-1">
          {description}
        </p>

        {/* Meta Info */}
        <div className="flex items-center justify-between text-xs text-navy-700 mb-3 gap-2">
          {location && (
            <div className="flex items-center gap-1 min-w-0 flex-shrink">
              <MapPin size={12} className="flex-shrink-0" />
              <span className="truncate">{location}</span>
            </div>
          )}
          {rating && (
            <div className="flex items-center gap-1 ml-auto flex-shrink-0">
              <Star size={12} className="fill-hype-yellow text-hype-yellow" />
              <span>{rating}</span>
            </div>
          )}
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
            <Heart size={14} className={isSaved ? 'fill-current' : ''} />
            <span className="text-xs font-medium">
              {isSaved ? srLabels.saved : srLabels.save}
            </span>
          </button>
          <button
            onClick={handleShare}
            className="flex-1 py-2 rounded-lg bg-hype-gray text-navy-600 hover:bg-hype-light transition-all duration-200 flex items-center justify-center gap-1"
          >
            <Share2 size={14} />
            <span className="text-xs font-medium">Deli</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default RecommendationCard;
