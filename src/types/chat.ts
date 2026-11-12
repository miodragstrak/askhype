export interface ChatHistoryItem {
  role: 'user' | 'assistant';
  text: string;
}

export interface PendingImage {
  file: File;
  previewUrl: string;
}

export interface PendingDocument {
  file: File;
}

export type DocumentAction = 'analyze' | 'transform' | 'presentation';

export interface TransformationDownload {
  filename: string;
  url?: string;
  available: boolean;
}

export interface DocumentMetadata {
  page_count: number | null;
  sheet_names: string[];
  rows_processed: number | null;
  columns_processed: number | null;
  extracted_characters: number;
  truncated: boolean;
}

export interface DocumentAnalysisResponse {
  filename: string;
  file_type: 'pdf' | 'docx' | 'xlsx' | 'csv';
  answer: string;
  extracted_metadata: DocumentMetadata;
  warnings: string[];
  generated_at: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  location?: string;
  language?: string;
  interests?: string[];
  history?: ChatHistoryItem[];
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
  download?: TransformationDownload;
  presentation_slide_count?: number;
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
