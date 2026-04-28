export interface Page {
  slug: string;
  title: string;
  content: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  authored_by: 'user' | 'agent';
}

export interface SearchResult {
  slug: string;
  title: string;
  excerpt: string;
  score: number;
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'page' | 'entity';
  entity_type?: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  label: string;
}

export interface IngestProgress {
  type: 'start' | 'parsed' | 'page_created' | 'page_updated' | 'done' | 'error';
  file?: string;
  slug?: string;
  title?: string;
  message?: string;
  pages_created?: number;
  pages_updated?: number;
}
