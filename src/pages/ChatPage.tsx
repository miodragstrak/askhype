import React, { useState } from 'react';
import { AppHeader, AskHypeInput, FilterChip, RecommendationCard, SourceVerification } from '../components';
import { destinations } from '../mock-data';

export const ChatPage: React.FC = () => {
  const [messages, setMessages] = useState<any[]>([
    {
      id: '1',
      role: 'user',
      content: 'Gde mogu da udem sutra uveče u Beogradu? Volim muziku i dobre pijače.',
    },
    {
      id: '2',
      role: 'assistant',
      content: 'Na osnovu tvojih preferencija, preporučujem ti sledeće destinacije koje su idealne za veče punog muzike i odličnih pića u Beogradu.',
    },
  ]);

  const handleMessageSubmit = (value: string) => {
    setMessages([
      ...messages,
      {
        id: String(messages.length + 1),
        role: 'user',
        content: value,
      },
      {
        id: String(messages.length + 2),
        role: 'assistant',
        content: 'Hvala na tvojoj poruci! Evo šta preporučujem...',
      },
    ]);
  };

  const recommendedDestinations = destinations.slice(0, 3);

  return (
    <div className="pb-28 md:pb-6 overflow-x-hidden">
      <AppHeader title="Pitaj" />

      <main className="max-w-md mx-auto px-4 py-6">
        {/* Conversation Title */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-navy-900">Veče u Beogradu</h1>
          <p className="text-sm text-navy-600">Početak: Sad</p>
        </div>

        {/* Context Chips */}
        <div className="flex gap-2 overflow-x-auto pb-4 mb-6 -mx-4 px-4 scrollbar-hide">
          <FilterChip label="📍 Beograd" variant="active" />
          <FilterChip label="🎵 Muzika" variant="active" />
          <FilterChip label="🍹 Noćni život" variant="active" />
        </div>

        {/* Chat Messages */}
        <div className="space-y-4 mb-6">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-xs rounded-2xl px-4 py-3 ${
                  msg.role === 'user'
                    ? 'bg-navy-900 text-hype-white rounded-br-none'
                    : 'bg-hype-gray text-navy-900 rounded-bl-none'
                }`}
              >
                <p className="text-sm">{msg.content}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Recommendations Section */}
        <div className="mb-6">
          <h2 className="text-sm font-bold text-navy-900 mb-4">Preporučeno za tebe</h2>
          <div className="grid grid-cols-2 gap-4 mb-4">
            {recommendedDestinations.slice(0, 2).map((dest) => (
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
          {recommendedDestinations.length > 2 && (
            <RecommendationCard
              id={recommendedDestinations[2].id}
              title={recommendedDestinations[2].name}
              description={recommendedDestinations[2].description}
              imageUrl={recommendedDestinations[2].imageUrl}
              location={recommendedDestinations[2].location.name}
              rating={recommendedDestinations[2].rating}
              category={recommendedDestinations[2].category.name}
              className="col-span-2"
            />
          )}
        </div>

        {/* Why Recommended */}
        <div className="bg-hype-gray rounded-2xl p-4 mb-6">
          <p className="text-xs font-semibold text-navy-900 mb-2">
            Zašto ti preporučujemo ove destinacije?
          </p>
          <ul className="text-xs text-navy-700 space-y-1">
            <li>✓ Odličnih je reputacija za noćni život</li>
            <li>✓ Predviđeno je zbog muzike i atraktivnog ambijenta</li>
            <li>✓ Često je gost sa sličnim interesima</li>
          </ul>
        </div>

        {/* Source Verification */}
        <SourceVerification
          verified={true}
          lastVerified="2024-07-25T18:00:00Z"
          source="AskHype Local"
          className="mb-6"
        />

        {/* Suggested Next Actions */}
        <div className="bg-hype-light rounded-2xl p-4 mb-6">
          <p className="text-xs font-semibold text-navy-900 mb-3">Šta dalje?</p>
          <div className="space-y-2">
            <button className="w-full text-left text-xs text-navy-700 hover:text-navy-900 py-2 px-2 hover:bg-hype-gray rounded transition">
              Detaljnije o prvoj preporuci
            </button>
            <button className="w-full text-left text-xs text-navy-700 hover:text-navy-900 py-2 px-2 hover:bg-hype-gray rounded transition">
              Prikaži mi druge tipove barova
            </button>
            <button className="w-full text-left text-xs text-navy-700 hover:text-navy-900 py-2 px-2 hover:bg-hype-gray rounded transition">
              Kreiraj plan za veče
            </button>
          </div>
        </div>
      </main>

      {/* Fixed Input at Bottom */}
      <div className="fixed bottom-0 left-0 right-0 bg-hype-white border-t border-hype-gray md:relative md:border-t-0 md:mt-6">
        <div className="max-w-md mx-auto px-4 py-4">
          <AskHypeInput
            placeholder="Postavi novo pitanje…"
            onSubmit={handleMessageSubmit}
          />
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
