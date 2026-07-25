import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { AppHeader, RecommendationCard, SourceVerification } from '../components';
import { destinations, events } from '../mock-data';
import { Heart, Share2, MapPin, Star, Clock } from 'lucide-react';
import { imageUtils, storageUtils } from '../utils';
import { srLabels } from '../constants/labels';

export const RecommendationDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [isSaved, setIsSaved] = useState(storageUtils.isSaved(id || ''));

  // Find the item (could be destination or event for now)
  const destination = destinations.find((d) => d.id === id);
  const event = events.find((e) => e.id === id);
  const item = destination || event;

  if (!item) {
    return (
      <div className="pb-24 md:pb-6">
        <AppHeader title="Detaljno" showBack onBack={() => navigate(-1)} />
        <div className="max-w-md mx-auto px-4 py-12 text-center">
          <p className="text-navy-600">Stavka nije pronađena</p>
          <button
            onClick={() => navigate('/')}
            className="mt-4 px-6 py-2 bg-navy-900 text-hype-white rounded-full text-sm font-medium"
          >
            Nazad na početnu
          </button>
        </div>
      </div>
    );
  }

  const handleSaveToggle = () => {
    const newSaved = !isSaved;
    setIsSaved(newSaved);
    if (newSaved) {
      storageUtils.addSavedItem(id || '');
    } else {
      storageUtils.removeSavedItem(id || '');
    }
  };

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({
        title: ('title' in item ? item.title : item.name),
        text: item.description,
      });
    }
  };

  const similarItems = 'name' in item ? destinations.filter((d) => d.id !== id).slice(0, 2) : events.filter((e) => e.id !== id).slice(0, 2);

  return (
    <div className="pb-28 md:pb-6 overflow-x-hidden">
      <AppHeader title="Detaljno" showBack onBack={() => navigate(-1)} />

      <main className="max-w-md mx-auto">
        {/* Hero Image */}
        <div className="relative h-64 overflow-hidden bg-hype-gray">
          <img
            src={imageUtils.getSafeSrc(item.imageUrl)}
            alt={'title' in item ? item.title : item.name}
            onError={imageUtils.onImageError}
            className="w-full h-full object-cover"
          />
          <button
            onClick={() => navigate(-1)}
            className="absolute top-4 left-4 bg-hype-white rounded-full p-2 shadow-lg"
          >
            ←
          </button>
        </div>

        <div className="px-4 py-6 space-y-6">
          {/* Key Info */}
          <div>
            <h1 className="text-3xl font-bold text-navy-900 mb-2">
              {'title' in item ? item.title : item.name}
            </h1>
            <div className="flex flex-wrap items-center gap-4 text-sm text-navy-700">
              {'location' in item && (
                <div className="flex items-center gap-1">
                  <MapPin size={16} />
                  <span>{item.location.name}</span>
                </div>
              )}
              {'rating' in item && (
                <div className="flex items-center gap-1">
                  <Star size={16} className="fill-hype-yellow text-hype-yellow" />
                  <span>{item.rating}</span>
                </div>
              )}
              {'price' in item && item.price && (
                <span className="font-semibold">{item.price} RSD</span>
              )}
              {'date' in item && (
                <div className="flex items-center gap-1">
                  <Clock size={16} />
                  <span>{new Date(item.date).toLocaleDateString('sr-RS')}</span>
                </div>
              )}
            </div>
          </div>

          {/* Category & Duration */}
          {('duration' in item) && (
            <div className="flex gap-2">
              <span className="px-3 py-1 bg-hype-yellow text-navy-900 rounded-full text-xs font-semibold">
                {item.category.name}
              </span>
              <span className="px-3 py-1 bg-hype-gray text-navy-700 rounded-full text-xs font-medium">
                {item.duration}
              </span>
            </div>
          )}

          {/* Description */}
          <div>
            <h2 className="text-sm font-bold text-navy-900 mb-2">Opis</h2>
            <p className="text-sm text-navy-700 leading-relaxed">
              {item.description}
            </p>
          </div>

          {/* Why Recommended */}
          <div className="bg-hype-gray rounded-2xl p-4">
            <h2 className="text-sm font-bold text-navy-900 mb-3">Zašto ti preporučujemo</h2>
            <ul className="text-xs text-navy-700 space-y-2">
              <li>✓ Odgovara tvojim interesima</li>
              <li>✓ Visoko je ocenjeno od strane korisnika</li>
              <li>✓ Blizu je tebi i dostupno</li>
            </ul>
          </div>

          {/* Practical Information */}
          {'bestTime' in item && (
            <div className="bg-hype-light rounded-2xl p-4">
              <h2 className="text-sm font-bold text-navy-900 mb-3">Praktične informacije</h2>
              <div className="space-y-2 text-xs text-navy-700">
                <p>
                  <span className="font-semibold">Najbolje vreme:</span> {item.bestTime}
                </p>
                <p>
                  <span className="font-semibold">Trajanje:</span> {item.duration}
                </p>
              </div>
            </div>
          )}

          {/* Source Verification */}
          <SourceVerification
            verified={true}
            lastVerified="2024-07-25T18:00:00Z"
            source="AskHype Local"
          />

          {/* Similar Items */}
          {similarItems.length > 0 && (
            <section>
              <h2 className="text-sm font-bold text-navy-900 mb-3">Slične stavke</h2>
              <div className="grid grid-cols-2 gap-4">
                {similarItems.map((item: any) => (
                  <RecommendationCard
                    key={item.id}
                    id={item.id}
                    title={item.name || item.title}
                    description={item.description}
                    imageUrl={item.imageUrl}
                    location={'location' in item ? item.location.name : undefined}
                    rating={'rating' in item ? item.rating : undefined}
                    category={item.category.name}
                    price={'price' in item ? item.price : undefined}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Actions */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={handleSaveToggle}
              className={`py-3 rounded-lg font-medium text-sm flex items-center justify-center gap-2 transition-all ${
                isSaved
                  ? 'bg-hype-yellow text-navy-900'
                  : 'bg-hype-gray text-navy-700 hover:bg-hype-light'
              }`}
            >
              <Heart size={18} className={isSaved ? 'fill-current' : ''} />
              <span>{isSaved ? srLabels.saved : srLabels.save}</span>
            </button>
            <button
              onClick={handleShare}
              className="py-3 rounded-lg font-medium text-sm bg-hype-gray text-navy-700 hover:bg-hype-light flex items-center justify-center gap-2 transition-all"
            >
              <Share2 size={18} />
              <span>Deli</span>
            </button>
          </div>

          {/* Additional Actions */}
          <div className="grid grid-cols-2 gap-3">
            <button className="py-3 rounded-lg font-medium text-sm bg-navy-900 text-hype-white hover:bg-navy-800 transition-all">
              Pitaj AskHype
            </button>
            <button className="py-3 rounded-lg font-medium text-sm bg-navy-900 text-hype-white hover:bg-navy-800 transition-all">
              Kreiraj plan
            </button>
          </div>
        </div>
      </main>
    </div>
  );
};

export default RecommendationDetailPage;
