import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AppHeader,
  AskHypeInput,
  QuickPromptChip,
  CategoryCircle,
  RecommendationCard,
  HypeContentCard,
  AskHypeLogo,
} from '../components';
import { categories, quickPrompts, destinations, hypeArticles } from '../mock-data';

export const HomePage: React.FC = () => {
  const navigate = useNavigate();

  const createPromptId = () => {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return crypto.randomUUID();
    }

    return `prompt-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  };

  const submitPromptToChat = (value: string) => {
    const text = value.trim();
    if (!text) return;

    navigate('/chat', {
      state: {
        initialPrompt: {
          id: createPromptId(),
          text,
        },
      },
    });
  };

  const categoryArray = Object.values(categories).slice(0, 6);
  const featuredDestinations = destinations.slice(0, 4);
  const featuredArticles = hypeArticles.slice(0, 2);

  return (
    <div className="pb-28 md:pb-6 overflow-x-hidden">
      <AppHeader compact location="Beograd" />

      <main className="max-w-md mx-auto px-4 py-4 space-y-6 md:px-6">
        {/* Logo Area */}
        <div className="flex flex-col items-center pt-2 text-center">
          <AskHypeLogo variant="full" className="mb-2" />
          <p className="text-xs md:text-sm text-navy-600">
            Otkrij zabavu, putovanja, događaje i stil života po Balkanu
          </p>
        </div>

        {/* Main Card */}
        <div className="bg-gradient-to-br from-hype-yellow to-yellow-100 rounded-3xl p-5 md:p-6">
          <p className="text-xl md:text-2xl font-bold text-navy-900 mb-4 text-center">
            Šta želiš da otkriješ?
          </p>
          <AskHypeInput
            placeholder="Pitaj AskHype…"
            onSubmit={submitPromptToChat}
            className="w-full"
          />
        </div>

        {/* Quick Prompts */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-navy-900">Brze pretrage</h2>
            <button className="text-xs font-semibold text-navy-900 hover:text-navy-700">
              Vidi sve →
            </button>
          </div>
          <div className="flex overflow-x-auto gap-2 px-4 pb-2 -mx-4 scrollbar-hide overscroll-x-contain">
            {quickPrompts.map((prompt) => (
              <div key={prompt.id} className="min-w-max flex-shrink-0">
                <QuickPromptChip
                  text={prompt.text}
                  iconName={prompt.icon}
                  onClick={() => submitPromptToChat(prompt.text)}
                  variant="outline"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Categories */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-navy-900">Kategorije</h2>
            <button className="text-xs font-semibold text-navy-900 hover:text-navy-700">
              Vidi sve →
            </button>
          </div>
          <div className="grid grid-cols-3 gap-3 md:gap-4">
            {categoryArray.map((category) => (
              <CategoryCircle
                key={category.id}
                name={category.name}
                iconName={category.icon}
                color={category.color}
                onClick={() => navigate('/explore')}
              />
            ))}
          </div>
        </div>

        {/* Recommended for You */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-navy-900">Preporučeno za tebe</h2>
            <button
              onClick={() => navigate('/explore')}
              className="text-xs font-semibold text-navy-900 hover:text-navy-700"
            >
              Vidi sve →
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3 md:gap-4">
            {featuredDestinations.map((dest) => (
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

        {/* Featured on Hype */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-navy-900">Aktuelno na Hype-u</h2>
            <button
              onClick={() => navigate('/explore')}
              className="text-xs font-semibold text-navy-900 hover:text-navy-700"
            >
              Vidi sve →
            </button>
          </div>
          <div className="space-y-3">
            {featuredArticles.map((article) => (
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
      </main>
    </div>
  );
};

export default HomePage;
