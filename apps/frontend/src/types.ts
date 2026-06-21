export interface Page {
  slug: string;
  title: string;
  content: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  authored_by: 'user' | 'agent';
}

export interface Folder {
  path: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface FolderMutationResult {
  path: string;
  pages: number;
  folders: number;
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
  type: 'start' | 'parsed' | 'extracting' | 'extracted' | 'page_created' | 'page_updated' | 'done' | 'error';
  file?: string;
  log_id?: number;
  source?: string;
  chars?: number;
  slug?: string;
  title?: string;
  message?: string;
  pages?: number;
  entities?: number;
  entities_extracted?: number;
  pages_created?: number;
  pages_updated?: number;
}

export interface IngestLog {
  id: number;
  wiki_id: string;
  source_type: 'file' | 'url' | 'batch';
  source_path: string;
  status: 'pending' | 'running' | 'done' | 'error';
  pages_created: number;
  pages_updated: number;
  error: string | null;
  created_at: string;
}

export type IngestSocketMessage =
  | { type: 'snapshot'; logs: IngestLog[] }
  | { type: 'event'; event: IngestProgress }
  | { type: 'control_ack'; action: string }
  | { type: 'control_error'; action?: string; message: string };

export type LifeProject = {
  id: number;
  key: string;
  name: string;
  status: string;
  page_slug?: string | null;
  summary: string;
  updated_at: string;
};

export type LifeTask = {
  id: number;
  title: string;
  status: string;
  project_key?: string | null;
  page_slug?: string | null;
  due_date?: string | null;
  source: string;
  updated_at: string;
};
