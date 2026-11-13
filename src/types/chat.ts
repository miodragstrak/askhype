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

export type DocumentAction = 'analyze' | 'transform' | 'presentation' | 'research';

export interface ResearchSection { heading: string; content: string; }
export interface ResearchSource { title: string; url: string; publisher?: string | null; date?: string | null; citation_ids?: number[]; display_label?: string | null; original_url?: string | null; }
export interface ResearchQuotaSnapshot { used: number; limit: number; remaining: number; reset_at: string; }
export interface ResearchResult {
  research_id: string;
  status: 'completed';
  title: string;
  summary: string;
  sections: ResearchSection[];
  sources: ResearchSource[];
  limitations: string[];
  generated_at: string;
  provider: string;
  model: string;
}
export interface ResearchJob {
  research_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  created_at: string;
  updated_at: string;
  result?: ResearchResult | null;
  failure_category?: string | null;
  quota?: ResearchQuotaSnapshot | null;
}

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
  research?: ResearchResult;
  research_quota_remaining?: number;
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
