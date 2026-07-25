export interface Location {
  id: string;
  name: string;
  country: string;
  lat: number;
  lng: number;
}

export interface Category {
  id: string;
  name: string;
  icon: string;
  color: string;
}

export interface Event {
  id: string;
  title: string;
  description: string;
  date: string;
  location: Location;
  imageUrl: string;
  category: Category;
  price?: number;
  duration?: string;
  isSaved?: boolean;
}

export interface Destination {
  id: string;
  name: string;
  description: string;
  imageUrl: string;
  location: Location;
  rating: number;
  category: Category;
  bestTime?: string;
  duration?: string;
  isSaved?: boolean;
}

export interface HypeArticle {
  id: string;
  title: string;
  excerpt: string;
  content: string;
  imageUrl: string;
  author: string;
  publishedAt: string;
  category: Category;
  readTime: number;
  isSaved?: boolean;
}

export interface Recommendation {
  id: string;
  title: string;
  type: 'event' | 'destination' | 'article';
  imageUrl: string;
  description: string;
  reason: string;
  sourceVerified: boolean;
  lastVerified?: string;
  isSaved?: boolean;
  content: Event | Destination | HypeArticle;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  context?: {
    location?: Location;
    language?: string;
    interests?: string[];
  };
}

export interface UserPreferences {
  city: string;
  country: string;
  language: string;
  currency: string;
  interests: string[];
  recommendationStyle: 'adventurous' | 'relaxed' | 'cultural' | 'balanced';
  savedItems: string[];
}

export interface QuickPrompt {
  id: string;
  text: string;
  icon: string;
}

export interface SavedItem {
  id: string;
  title: string;
  type: 'event' | 'destination' | 'article';
  imageUrl: string;
  category: string;
  savedAt: string;
}
