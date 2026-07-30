export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  location?: string;
  language?: string;
  interests?: string[];
}

export interface ChatResponse {
  conversation_id: string;
  provider: string;
  answer_type: string;
  summary: string;
  recommendations: ChatRecommendation[];
  follow_up_actions: string[];
  sources: SourceReference[];
  generated_at: string;
}

export interface ChatRecommendation {
  id: string;
  title: string;
  category: string;
  short_description: string;
  location: string;
  estimated_price?: string | null;
  date_or_duration?: string | null;
  reason: string;
  image_url?: string | null;
  source_url?: string | null;
}

export interface SourceReference {
  title: string;
  url?: string | null;
  last_verified?: string | null;
}
