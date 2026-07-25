import React, { useState, useEffect } from 'react';
import { AppHeader, RecommendationCard, HypeContentCard, EmptyState, FilterChip } from '../components';
import { destinations, events, hypeArticles, categories } from '../mock-data';
import { Heart } from 'lucide-react';
import { storageUtils } from '../utils';
import { srLabels } from '../constants/labels';

export const SavedPage: React.FC = () => {
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [savedItems, setSavedItems] = useState<string[]>([]);

  useEffect(() => {
    setSavedItems(storageUtils.getSavedItems());
  }, []);

  const handleCategoryToggle = (categoryId: string) => {
    setSelectedCategories((prev) =>
      prev.includes(categoryId)
        ? prev.filter((id) => id !== categoryId)
        : [...prev, categoryId]
    );
  };

  // Filter saved items
  const filteredDestinations = destinations.filter((dest) => {
    if (!savedItems.includes(dest.id)) return false;
    if (selectedCategories.length === 0) return true;
    return selectedCategories.includes(dest.category.id);
  });

  const filteredEvents = events.filter((event) => {
    if (!savedItems.includes(event.id)) return false;
    if (selectedCategories.length === 0) return true;
    return selectedCategories.includes(event.category.id);
  });

  const filteredArticles = hypeArticles.filter((article) => {
    if (!savedItems.includes(article.id)) return false;
    if (selectedCategories.length === 0) return true;
    return selectedCategories.includes(article.category.id);
  });

  const totalSaved = filteredDestinations.length + filteredEvents.length + filteredArticles.length;

  const handleRemoveSavedItem = (itemId: string) => {
    storageUtils.removeSavedItem(itemId);
    setSavedItems((prev) => prev.filter((id) => id !== itemId));
  };

  const categoryArray = Object.values(categories);

  if (savedItems.length === 0) {
    return (
      <div className="pb-28 md:pb-6 overflow-x-hidden">
        <AppHeader title={srLabels.saved} />
        <main className="max-w-md mx-auto">
          <EmptyState
            icon={<Heart size={48} className="text-navy-600 mx-auto" />}
            title="Nema sačuvanih stavki"
            description="Počni da čuvaš stavke koje te zanimaju. Svi će biti dostupni ovde."
            action={{
              label: 'Istraži sadržaj',
              onClick: () => window.location.href = '/explore',
            }}
            className="mt-12"
          />
        </main>
      </div>
    );
  }

  return (
    <div className="pb-24 md:pb-6">
      <AppHeader title={srLabels.saved} />

      <main className="max-w-md mx-auto px-4 py-6 space-y-6">
        {/* Category Filters */}
        <div>
          <h3 className="text-xs font-semibold text-navy-900 mb-3 uppercase">Filtriraj po kategoriji</h3>
          <div className="flex overflow-x-auto gap-2 pb-2 -mx-4 px-4 scrollbar-hide">
            {categoryArray.map((category) => (
              <FilterChip
                key={category.id}
                label={category.name}
                onClick={() => handleCategoryToggle(category.id)}
                selected={selectedCategories.includes(category.id)}
                variant={selectedCategories.includes(category.id) ? 'active' : 'default'}
              />
            ))}
          </div>
        </div>

        {/* Stats */}
        <div className="bg-hype-gray rounded-2xl p-4">
          <p className="text-sm font-semibold text-navy-900">
            {totalSaved} sačuvane stavke
            {selectedCategories.length > 0 && ` (prikazane)`}
          </p>
        </div>

        {/* Destinations */}
        {filteredDestinations.length > 0 && (
          <section>
            <h2 className="text-sm font-bold text-navy-900 mb-3">Destinacije</h2>
            <div className="grid grid-cols-2 gap-4">
              {filteredDestinations.map((dest) => (
                <RecommendationCard
                  key={dest.id}
                  id={dest.id}
                  title={dest.name}
                  description={dest.description}
                  imageUrl={dest.imageUrl}
                  location={dest.location.name}
                  rating={dest.rating}
                  category={dest.category.name}
                  isSaved={true}
                  onSaveChange={(saved) => {
                    if (!saved) handleRemoveSavedItem(dest.id);
                  }}
                />
              ))}
            </div>
          </section>
        )}

        {/* Events */}
        {filteredEvents.length > 0 && (
          <section>
            <h2 className="text-sm font-bold text-navy-900 mb-3">Događaji</h2>
            <div className="space-y-4">
              {filteredEvents.map((event) => (
                <RecommendationCard
                  key={event.id}
                  id={event.id}
                  title={event.title}
                  description={event.description}
                  imageUrl={event.imageUrl}
                  location={event.location.name}
                  category={event.category.name}
                  price={event.price}
                  isSaved={true}
                  onSaveChange={(saved) => {
                    if (!saved) handleRemoveSavedItem(event.id);
                  }}
                />
              ))}
            </div>
          </section>
        )}

        {/* Articles */}
        {filteredArticles.length > 0 && (
          <section>
            <h2 className="text-sm font-bold text-navy-900 mb-3">Članki</h2>
            <div className="space-y-4">
              {filteredArticles.map((article) => (
                <HypeContentCard
                  key={article.id}
                  id={article.id}
                  title={article.title}
                  excerpt={article.excerpt}
                  imageUrl={article.imageUrl}
                  author={article.author}
                  readTime={article.readTime}
                  category={article.category.name}
                  isSaved={true}
                  onSaveChange={(saved) => {
                    if (!saved) handleRemoveSavedItem(article.id);
                  }}
                />
              ))}
            </div>
          </section>
        )}

        {/* No Results for Filters */}
        {totalSaved > 0 && filteredDestinations.length === 0 && filteredEvents.length === 0 && filteredArticles.length === 0 && (
          <div className="text-center py-12">
            <p className="text-navy-600 text-sm mb-4">Nema sačuvanih stavki u odabranim kategorijama</p>
            <button
              onClick={() => setSelectedCategories([])}
              className="px-6 py-2 bg-navy-900 text-hype-white rounded-full font-medium text-sm hover:bg-navy-800 transition-colors"
            >
              Očisti filtere
            </button>
          </div>
        )}
      </main>
    </div>
  );
};

export default SavedPage;
