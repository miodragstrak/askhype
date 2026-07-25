import React, { useState } from 'react';
import { AppHeader, AskHypeInput, FilterChip, RecommendationCard, HypeContentCard } from '../components';
import { categories, destinations, events, hypeArticles } from '../mock-data';

export const ExplorePage: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);

  const handleCategoryToggle = (categoryId: string) => {
    setSelectedCategories((prev) =>
      prev.includes(categoryId)
        ? prev.filter((id) => id !== categoryId)
        : [...prev, categoryId]
    );
  };

  const categoryArray = Object.values(categories);

  // Filter items based on search and selected categories
  const filteredDestinations = destinations.filter((dest) => {
    const matchesSearch = dest.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategories.length === 0 || selectedCategories.includes(dest.category.id);
    return matchesSearch && matchesCategory;
  });

  const filteredEvents = events.filter((event) => {
    const matchesSearch = event.title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategories.length === 0 || selectedCategories.includes(event.category.id);
    return matchesSearch && matchesCategory;
  });

  const filteredArticles = hypeArticles.filter((article) => {
    const matchesSearch = article.title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategories.length === 0 || selectedCategories.includes(article.category.id);
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="pb-28 md:pb-6 overflow-x-hidden">
      <AppHeader title="Istraži" />

      <main className="max-w-md mx-auto px-4 py-6 space-y-6">
        {/* Search */}
        <div>
          <AskHypeInput
            placeholder="Traži destinacije, događaje..."
            showSendButton={false}
            onSubmit={setSearchQuery}
            className="w-full"
          />
        </div>

        {/* Category Filters */}
        <div>
          <h3 className="text-xs font-semibold text-navy-900 mb-3 uppercase">Kategorije</h3>
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

        {/* Active Filters Display */}
        {selectedCategories.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            {selectedCategories.map((catId) => {
              const category = categories[Object.keys(categories).find((k) => categories[k as keyof typeof categories].id === catId) as keyof typeof categories];
              return (
                <FilterChip
                  key={catId}
                  label={category?.name || catId}
                  removable
                  onRemove={() => handleCategoryToggle(catId)}
                />
              );
            })}
          </div>
        )}

        {/* Recommended Items */}
        {filteredDestinations.length > 0 && (
          <section>
            <h2 className="text-sm font-bold text-navy-900 mb-3">Preporučene destinacije</h2>
            <div className="grid grid-cols-2 gap-4">
              {filteredDestinations.slice(0, 4).map((dest) => (
                <RecommendationCard
                  key={dest.id}
                  id={dest.id}
                  title={dest.name}
                  description={dest.description}
                  imageUrl={dest.imageUrl}
                  location={dest.location.name}
                  rating={dest.rating}
                  category={dest.category.name}
                />
              ))}
            </div>
          </section>
        )}

        {/* Popular Events */}
        {filteredEvents.length > 0 && (
          <section>
            <h2 className="text-sm font-bold text-navy-900 mb-3">Događaji</h2>
            <div className="space-y-4">
              {filteredEvents.slice(0, 3).map((event) => (
                <RecommendationCard
                  key={event.id}
                  id={event.id}
                  title={event.title}
                  description={event.description}
                  imageUrl={event.imageUrl}
                  location={event.location.name}
                  category={event.category.name}
                  price={event.price}
                />
              ))}
            </div>
          </section>
        )}

        {/* Hype Content */}
        {filteredArticles.length > 0 && (
          <section>
            <h2 className="text-sm font-bold text-navy-900 mb-3">Članki na Hype-u</h2>
            <div className="space-y-4">
              {filteredArticles.slice(0, 2).map((article) => (
                <HypeContentCard
                  key={article.id}
                  id={article.id}
                  title={article.title}
                  excerpt={article.excerpt}
                  imageUrl={article.imageUrl}
                  author={article.author}
                  readTime={article.readTime}
                  category={article.category.name}
                />
              ))}
            </div>
          </section>
        )}

        {/* No Results */}
        {filteredDestinations.length === 0 &&
          filteredEvents.length === 0 &&
          filteredArticles.length === 0 && (
            <div className="text-center py-12">
              <p className="text-navy-600 text-sm mb-4">Nema rezultata za tvoju pretragu</p>
              <button
                onClick={() => {
                  setSearchQuery('');
                  setSelectedCategories([]);
                }}
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

export default ExplorePage;
