import type {
  Page,
  Folder,
  FolderMutationResult,
  SearchResult,
  GraphNode,
  GraphEdge,
  IngestLog,
  IngestSocketMessage,
  LifeProject,
  LifeTask,
} from './types';

const BASE = '';

function getCookie(name: string): string | undefined {
  const match = document.cookie
    .split(';')
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${name}=`));
  if (!match) return undefined;
  return decodeURIComponent(match.substring(name.length + 1));
}

function csrfToken(): string | undefined {
  return getCookie('csrf_token');
}

function shouldSendCsrf(method?: string): boolean {
  const m = (method ?? 'GET').toUpperCase();
  return m === 'POST' || m === 'PUT' || m === 'PATCH' || m === 'DELETE';
}

function encodeSlugPath(slug: string): string {
  // Keep '/' as path separators but encode each segment safely.
  return slug
    .split('/')
    .map((seg) => encodeURIComponent(seg))
    .join('/');
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? 'GET').toUpperCase();
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
      ...(shouldSendCsrf(method)
        ? csrfToken()
          ? { 'X-CSRF-Token': csrfToken() }
          : {}
        : {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res;
}

export type CreatePageInput = {
  title: string;
  content?: string;
  tags?: string[];
  slug?: string;
};

export type UpdatePageInput = {
  title?: string | null;
  content?: string | null;
  tags?: string[] | null;
};

export type AuthSession = {
  username: string;
  role: string;
  wiki_id: string;
};

export async function login(password: string): Promise<void> {
  await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}

export async function refreshSession(): Promise<AuthSession> {
  const res = await apiFetch('/api/auth/refresh', { method: 'POST' });
  return res.json();
}

export async function logout(): Promise<void> {
  await apiFetch('/api/auth/logout', { method: 'POST' });
}

export async function listPages(): Promise<Page[]> {
  const res = await apiFetch('/api/pages');
  return res.json();
}

export async function getPage(slug: string): Promise<Page> {
  const res = await apiFetch(`/api/pages/${encodeSlugPath(slug)}`);
  return res.json();
}

export async function updatePage(slug: string, input: UpdatePageInput): Promise<Page> {
  const res = await apiFetch(`/api/pages/${encodeSlugPath(slug)}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function createPage(input: CreatePageInput): Promise<Page> {
  const res = await apiFetch('/api/pages', {
    method: 'POST',
    body: JSON.stringify({
      title: input.title,
      content: input.content ?? '',
      tags: input.tags ?? [],
      slug: input.slug,
    }),
  });
  return res.json();
}

export async function deletePage(slug: string): Promise<void> {
  await apiFetch(`/api/pages/${encodeSlugPath(slug)}`, { method: 'DELETE' });
}

export async function movePage(slug: string, input: { new_slug: string }): Promise<Page> {
  const res = await apiFetch(`/api/pages/${encodeSlugPath(slug)}/move`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function duplicatePage(
  slug: string,
  input: { new_slug: string; title?: string },
): Promise<Page> {
  const res = await apiFetch(`/api/pages/${encodeSlugPath(slug)}/duplicate`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function listFolders(): Promise<Folder[]> {
  const res = await apiFetch('/api/folders');
  return res.json();
}

export async function createFolder(input: { path: string }): Promise<Folder> {
  const res = await apiFetch('/api/folders', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function renameFolder(
  path: string,
  input: { name: string; recursive?: boolean },
): Promise<FolderMutationResult> {
  const res = await apiFetch(`/api/folders/${encodeSlugPath(path)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function moveFolder(
  path: string,
  input: { new_path: string; recursive?: boolean },
): Promise<FolderMutationResult> {
  const res = await apiFetch(`/api/folders/${encodeSlugPath(path)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function deleteFolder(
  path: string,
  input: { recursive?: boolean } = {},
): Promise<FolderMutationResult> {
  const recursive = input.recursive ? 'true' : 'false';
  const res = await apiFetch(`/api/folders/${encodeSlugPath(path)}?recursive=${recursive}`, {
    method: 'DELETE',
  });
  return res.json();
}

export async function getBacklinks(slug: string): Promise<Page[]> {
  const res = await apiFetch(`/api/pages/${encodeSlugPath(slug)}/backlinks`);
  return res.json();
}

export type SharePage = {
  type: string;
  token: string;
  wiki_id: string;
  slug: string | null;
  title: string | null;
  content: string | null;
  tags: string[];
  question: string | null;
  answer: string | null;
  citations: Array<{ slug: string; title: string }>;
  expires_at: string | null;
};

export async function getShare(token: string): Promise<SharePage> {
  // Share tokens are url-safe base64-ish; still encode defensively.
  const res = await apiFetch(`/api/share/${encodeURIComponent(token)}`);
  return res.json();
}

export type ShareLinkInfo = {
  id: number;
  token: string;
  type: string;
  target_id: string | null;
  created_at: string;
  expires_at: string | null;
  revoked: number;
};

export type CreateShareLinkInput = {
  type: 'page' | 'query';
  target_id?: string | null;
  question?: string;
  answer?: string;
  citations?: Array<{ slug: string; title: string }>;
  expires_in_days?: number | null;
};

export async function createShareLink(
  input: CreateShareLinkInput,
): Promise<{ token: string; url: string; expires_at: string | null }> {
  const res = await apiFetch('/api/share-links', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function listShareLinks(): Promise<ShareLinkInfo[]> {
  const res = await apiFetch('/api/share-links');
  return res.json();
}

export async function revokeShareLink(token: string): Promise<void> {
  await apiFetch(`/api/share-links/${token}`, { method: 'DELETE' });
}

export type PublicPageSummary = {
  slug: string;
  title: string;
  tags: string[];
  updated_at: string;
};

export type PublicPage = PublicPageSummary & {
  content: string;
};

export async function listPublicPages(): Promise<PublicPageSummary[]> {
  const res = await apiFetch('/api/public/pages');
  return res.json();
}

export async function getPublicPage(slug: string): Promise<PublicPage> {
  const res = await apiFetch(`/api/public/pages/${encodeSlugPath(slug)}`);
  return res.json();
}

export async function search(query: string): Promise<SearchResult[]> {
  const res = await apiFetch(`/api/search?q=${encodeURIComponent(query)}`);
  return res.json();
}

export async function getGraph(): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  const res = await apiFetch('/api/graph');
  return res.json();
}

export type Citation = {
  source_id: string;
  chunk_id: string;
  span_start: number | null;
  span_end: number | null;
  quote: string | null;
};

export type ContextNode = {
  id: string;
  label: string;
  node_type: string;
  scope: string;
  extraction_method: 'EXTRACTED' | 'INFERRED' | 'AMBIGUOUS' | 'USER_AUTHORED';
  confidence: number;
  citations: Citation[];
};

export type ContextEdge = {
  from_id: string;
  to_id: string;
  relation: string;
  scope: string;
  extraction_method: 'EXTRACTED' | 'INFERRED' | 'AMBIGUOUS' | 'USER_AUTHORED';
  confidence: number;
  citations: Citation[];
};

export type ContextPackage = {
  query: string;
  seeds: string[];
  nodes: ContextNode[];
  edges: ContextEdge[];
  citations: Citation[];
  insufficient_evidence: boolean;
  reason: string | null;
};

export type ContextPackageRequest = {
  query?: string;
  scope?: string;
  source_type?: string;
  depth?: number;
  max_nodes?: number;
  relations?: string[];
  seed_ids?: string[];
};

export type RetrievalHit = {
  id: string;
  label: string;
  score: number;
  source: string;
  citation: Citation;
  citations: Citation[];
  extraction_method: ContextNode['extraction_method'] | 'DERIVED' | null;
  confidence: number | null;
  provenance: 'canonical' | 'derived';
};

export type RetrieveResponse = {
  query: string;
  hits: RetrievalHit[];
  citations: Citation[];
  insufficient_evidence: boolean;
  reason: string | null;
};

export type MemorySuggestion = {
  id: string;
  target_id: string;
  suggestion_type: string;
  proposed_markdown: string;
  proposed_objects: unknown[];
  citations: Citation[];
  status: SuggestionStatus;
};

export type SuggestionStatus =
  | 'pending'
  | 'accepted'
  | 'edited'
  | 'rejected'
  | 'merged'
  | 'replaced'
  | 'kept'
  | 'retired'
  | 'scope_changed'
  | 'visibility_changed'
  | 'expired';

export type SuggestionReviewAction =
  | 'accept'
  | 'edit'
  | 'reject'
  | 'merge'
  | 'replace'
  | 'keep_both'
  | 'retire'
  | 'change_scope'
  | 'change_visibility'
  | 'expire';

export type CreateSuggestionInput = {
  target_id?: string;
  page_slug?: string;
  suggestion_type: string;
  proposed_markdown?: string;
  proposed_objects?: unknown[];
  citations?: Citation[];
};

export async function listSuggestions(): Promise<MemorySuggestion[]> {
  const res = await apiFetch('/api/suggestions');
  return res.json();
}

export async function listPageSuggestions(slug: string): Promise<MemorySuggestion[]> {
  const res = await apiFetch(`/api/suggestions?page_slug=${encodeURIComponent(slug)}`);
  return res.json();
}

export async function createSuggestion(input: CreateSuggestionInput): Promise<MemorySuggestion> {
  const res = await apiFetch('/api/suggestions', {
    method: 'POST',
    body: JSON.stringify({
      target_id: input.target_id,
      page_slug: input.page_slug,
      suggestion_type: input.suggestion_type,
      proposed_markdown: input.proposed_markdown ?? '',
      proposed_objects: input.proposed_objects ?? [],
      citations: input.citations ?? [],
    }),
  });
  return res.json();
}

export async function acceptSuggestion(suggestionId: string): Promise<MemorySuggestion> {
  const res = await apiFetch(`/api/suggestions/${encodeURIComponent(suggestionId)}/accept`, {
    method: 'POST',
  });
  return res.json();
}

export async function rejectSuggestion(suggestionId: string): Promise<MemorySuggestion> {
  const res = await apiFetch(`/api/suggestions/${encodeURIComponent(suggestionId)}/reject`, {
    method: 'POST',
  });
  return res.json();
}

export async function reviewSuggestion(
  suggestionId: string,
  action: SuggestionReviewAction,
): Promise<MemorySuggestion> {
  const res = await apiFetch(`/api/suggestions/${encodeURIComponent(suggestionId)}/review`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  });
  return res.json();
}

// ── Memory assets, loadouts, and distillation ───────────────────────────────

export type MemoryAssetType =
  | 'wiki'
  | 'chat'
  | 'skill'
  | 'codegraph'
  | 'source'
  | 'scenario'
  | 'persona';

export type MemoryLayer = 'L0' | 'L1' | 'L2' | 'L3';

export type MemoryAsset = {
  id: string;
  wiki_id: string;
  asset_type: MemoryAssetType;
  layer: MemoryLayer;
  name: string;
  owner: string;
  scope: string;
  status: 'draft' | 'active' | 'archived';
  visibility: 'private' | 'shared' | 'public';
  version: number;
  page_slug: string | null;
  summary: string;
  body: string;
  tags: string[];
  metadata: Record<string, unknown>;
  citations: Citation[];
  created_at: string;
  updated_at: string;
};

export type MemoryAssetVersion = {
  asset_id: string;
  version: number;
  name: string;
  summary: string;
  body: string;
  status: string;
  change_note: string;
  created_at: string;
};

export type AgentProfile = {
  agent_key: string;
  wiki_id: string;
  name: string;
  description: string;
};

export type AssetBinding = {
  agent_key: string;
  asset_id: string;
  mode: 'always' | 'on_demand';
  priority: number;
};

export type LoadoutEntry = {
  asset: MemoryAsset;
  mode: 'always' | 'on_demand';
  priority: number;
  reason: string;
};

export type LoadoutPackage = {
  agent_key: string;
  query: string;
  entries: LoadoutEntry[];
  citations: Citation[];
  insufficient_evidence: boolean;
  reason: string | null;
};

export type DistillReport = {
  source_id: string;
  session_id: string;
  scope: string;
  atoms_total: number;
  atoms_accepted: number;
  atoms_pending_review: number;
  asset_ids: string[];
  scenario_id: string | null;
  persona_updated: boolean;
  skill_id: string | null;
  skill_reason: string | null;
  pages_written: string[];
};

export async function listMemoryAssets(
  filters: { asset_type?: string; layer?: string; status?: string } = {},
): Promise<MemoryAsset[]> {
  const params = new URLSearchParams();
  if (filters.asset_type) params.set('asset_type', filters.asset_type);
  if (filters.layer) params.set('layer', filters.layer);
  if (filters.status) params.set('status', filters.status);
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const res = await apiFetch(`/api/memory/assets${suffix}`);
  return res.json();
}

export async function getMemoryAsset(assetId: string): Promise<MemoryAsset> {
  const res = await apiFetch(`/api/memory/assets/${encodeURIComponent(assetId)}`);
  return res.json();
}

export async function listMemoryAssetVersions(assetId: string): Promise<MemoryAssetVersion[]> {
  const res = await apiFetch(`/api/memory/assets/${encodeURIComponent(assetId)}/versions`);
  return res.json();
}

export async function setMemoryAssetStatus(
  assetId: string,
  status: 'draft' | 'active' | 'archived',
): Promise<MemoryAsset> {
  const res = await apiFetch(`/api/memory/assets/${encodeURIComponent(assetId)}/status`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  });
  return res.json();
}

export async function setMemoryAssetVisibility(
  assetId: string,
  visibility: 'private' | 'shared' | 'public',
): Promise<MemoryAsset> {
  const res = await apiFetch(`/api/memory/assets/${encodeURIComponent(assetId)}/visibility`, {
    method: 'POST',
    body: JSON.stringify({ visibility }),
  });
  return res.json();
}

export async function listMemoryAgents(): Promise<AgentProfile[]> {
  const res = await apiFetch('/api/memory/agents');
  return res.json();
}

export async function upsertMemoryAgent(input: {
  agent_key: string;
  name: string;
  description?: string;
}): Promise<AgentProfile> {
  const res = await apiFetch('/api/memory/agents', {
    method: 'POST',
    body: JSON.stringify({ ...input, description: input.description ?? '' }),
  });
  return res.json();
}

export async function listAgentBindings(agentKey: string): Promise<AssetBinding[]> {
  const res = await apiFetch(`/api/memory/agents/${encodeURIComponent(agentKey)}/bindings`);
  return res.json();
}

export async function bindMemoryAsset(
  agentKey: string,
  input: { asset_id: string; mode?: 'always' | 'on_demand'; priority?: number },
): Promise<AssetBinding> {
  const res = await apiFetch(`/api/memory/agents/${encodeURIComponent(agentKey)}/bindings`, {
    method: 'POST',
    body: JSON.stringify({
      asset_id: input.asset_id,
      mode: input.mode ?? 'always',
      priority: input.priority ?? 100,
    }),
  });
  return res.json();
}

export async function unbindMemoryAsset(
  agentKey: string,
  assetId: string,
): Promise<{ removed: boolean }> {
  const res = await apiFetch(
    `/api/memory/agents/${encodeURIComponent(agentKey)}/bindings/${encodeURIComponent(assetId)}`,
    { method: 'DELETE' },
  );
  return res.json();
}

export async function getAgentLoadout(
  agentKey: string,
  query = '',
): Promise<LoadoutPackage> {
  const suffix = query ? `?query=${encodeURIComponent(query)}` : '';
  const res = await apiFetch(
    `/api/memory/agents/${encodeURIComponent(agentKey)}/loadout${suffix}`,
  );
  return res.json();
}

export type CatalogReport = {
  wiki_assets: number;
  source_assets: number;
  codegraph_assets: number;
  asset_ids: string[];
};

export async function catalogMemoryAssets(): Promise<CatalogReport> {
  const res = await apiFetch('/api/memory/catalog', { method: 'POST' });
  return res.json();
}

export async function distillSource(input: {
  source_id: string;
  scenario_key?: string;
  threshold?: number;
  write_pages?: boolean;
}): Promise<DistillReport> {
  const res = await apiFetch('/api/memory/distill', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return res.json();
}

export type CaptureTurnInput = {
  role: 'system' | 'user' | 'assistant' | 'tool' | string;
  text: string;
  ts?: string;
  tool_calls?: Array<{
    name: string;
    arguments?: Record<string, unknown>;
    result?: string | null;
    call_id?: string | null;
    ok?: boolean;
  }>;
};

export type CaptureConversationInput = {
  session_id: string;
  interface?: string;
  started_at?: string;
  turns: CaptureTurnInput[];
  scope?: string;
  origin_uri?: string;
};

export type CaptureResponse = {
  source_id: string;
  content_hash: string;
  version: number;
  document_id: string;
  chunk_count: number;
  deduplicated: boolean;
};

export async function captureConversation(
  input: CaptureConversationInput,
): Promise<CaptureResponse> {
  const res = await apiFetch('/api/sources/capture', {
    method: 'POST',
    body: JSON.stringify({
      session_id: input.session_id,
      interface: input.interface ?? 'archivum_home',
      started_at: input.started_at ?? '',
      scope: input.scope ?? 'person:self',
      origin_uri: input.origin_uri ?? '',
      turns: input.turns.map((turn) => ({
        role: turn.role,
        text: turn.text,
        ts: turn.ts ?? '',
        tool_calls: (turn.tool_calls ?? []).map((call) => ({
          name: call.name,
          arguments: call.arguments ?? {},
          result: call.result ?? null,
          call_id: call.call_id ?? null,
          ok: call.ok ?? true,
        })),
      })),
    }),
  });
  return res.json();
}

// ── Graph audit ─────────────────────────────────────────────────────────────

export type GraphCommunity = {
  id: string;
  label: string;
  size: number;
  member_ids: string[];
};

export type SurprisingLink = {
  src_id: string;
  dst_id: string;
  src_label: string;
  dst_label: string;
  rel_type: string;
  score: number;
  neighbor_overlap: number;
  cross_community: boolean;
  reason: string;
};

export type GraphReport = {
  scope: string | null;
  node_count: number;
  edge_count: number;
  by_kind: Record<string, number>;
  by_extraction_method: Record<string, number>;
  self_cited_ids: string[];
  low_confidence_ids: string[];
  orphan_ids: string[];
  communities: GraphCommunity[];
  surprising_links: SurprisingLink[];
  narrative: string[];
};

export type GraphPathResult = {
  source: string;
  target: string;
  found: boolean;
  length: number;
  steps: { from_id: string; to_id: string; relation: string }[];
  reason: string | null;
};

export async function getGraphAudit(surpriseLimit = 10): Promise<GraphReport> {
  const res = await apiFetch(`/api/graph/audit?surprise_limit=${surpriseLimit}`);
  return res.json();
}

export async function getGraphPath(source: string, target: string): Promise<GraphPathResult> {
  const res = await apiFetch(
    `/api/graph/path?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`,
  );
  return res.json();
}

export async function getContextPackage(
  input: ContextPackageRequest = {},
): Promise<ContextPackage> {
  const res = await apiFetch('/api/context-package', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function retrieveContext(input: { query: string; limit?: number }): Promise<RetrieveResponse> {
  const res = await apiFetch('/api/retrieve', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function ensureDailyNote(date?: string): Promise<Page> {
  const res = await apiFetch('/api/life/daily', {
    method: 'POST',
    body: JSON.stringify({ date }),
  });
  return res.json();
}

export async function listLifeProjects(): Promise<LifeProject[]> {
  const res = await apiFetch('/api/life/projects');
  return res.json();
}

export async function createLifeProject(input: {
  key: string;
  name: string;
  summary?: string;
  status?: string;
}): Promise<LifeProject> {
  const res = await apiFetch('/api/life/projects', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function listLifeTasks(status?: string): Promise<LifeTask[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  const res = await apiFetch(`/api/life/tasks${qs}`);
  return res.json();
}

export async function createLifeTask(input: {
  title: string;
  project_key?: string;
  page_slug?: string;
  due_date?: string;
}): Promise<LifeTask> {
  const res = await apiFetch('/api/life/tasks', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return res.json();
}

async function parseSSEStream(
  response: Response,
  onEvent: (data: unknown) => void,
): Promise<void> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';

    for (const part of parts) {
      const lines = part.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') return;
          try {
            onEvent(JSON.parse(raw));
          } catch {
            // non-JSON data line — ignore
          }
        }
      }
    }
  }
}

export async function ingestFile(
  file: File,
): Promise<{ accepted: boolean; file: string | null }> {
  const formData = new FormData();
  formData.append('file', file);

  const csrf = csrfToken();
  const response = await fetch('/api/ingest/file', {
    method: 'POST',
    credentials: 'include',
    body: formData,
    ...(csrf ? { headers: { 'X-CSRF-Token': csrf } } : {}),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(text || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function ingestUrl(
  url: string,
): Promise<{ accepted: boolean; url: string | null }> {
  const csrf = csrfToken();
  const response = await fetch('/api/ingest/url', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
    },
    body: JSON.stringify({ url }),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(text || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function listIngestHistory(limit = 25): Promise<IngestLog[]> {
  const res = await apiFetch(`/api/ingest/history?limit=${encodeURIComponent(String(limit))}`);
  return res.json();
}

export function openIngestSocket(
  onMessage: (message: IngestSocketMessage) => void,
  onClose?: () => void,
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${protocol}//${window.location.host}/api/ingest/ws`);

  socket.addEventListener('message', (event) => {
    try {
      onMessage(JSON.parse(event.data) as IngestSocketMessage);
    } catch {
      // Ignore malformed socket messages.
    }
  });
  if (onClose) {
    socket.addEventListener('close', onClose);
  }
  return socket;
}

export type InviteToken = {
  id: number;
  wiki_id: string;
  token: string;
  role: string;
  created_by: string;
  created_at: string;
  expires_at: string | null;
  used: number;
};

export type LintIssue = {
  type: string;
  page: string;
  target?: string;
  suggestion: string;
};

export type AudioSupportStatus = {
  available: boolean;
  dependencies: {
    openai_whisper: boolean;
    ffmpeg: boolean;
  };
  missing: string[];
  commands: {
    local: string;
    ffmpeg: string;
    docker: string;
  };
  notes: string[];
};

export async function createInvite(
  role: 'viewer' | 'collaborator',
  expires_in_days: number | null,
): Promise<{ token: string; url: string; role: string; expires_at: string | null }> {
  const res = await apiFetch('/api/auth/invites', {
    method: 'POST',
    body: JSON.stringify({ role, expires_in_days }),
  });
  return res.json();
}

export async function listInvites(): Promise<InviteToken[]> {
  const res = await apiFetch('/api/auth/invites');
  return res.json();
}

export async function getAudioSupport(): Promise<AudioSupportStatus> {
  const res = await apiFetch('/api/audio-support');
  return res.json();
}

export type LlmSettings = {
  llm_extraction_provider: string;
  llm_synthesis_provider: string;
  llm_model: string;
  llm_synthesis_model: string;
  ollama_base_url: string;
  ollama_api_key_configured: boolean;
  ollama_api_key_masked: string;
};

export type UpdateLlmSettingsInput = {
  llm_extraction_provider: string;
  llm_synthesis_provider: string;
  llm_model: string;
  llm_synthesis_model: string;
  ollama_base_url: string;
  ollama_api_key?: string | null;
};

export async function getLlmSettings(): Promise<LlmSettings> {
  const res = await apiFetch('/api/settings/llm');
  return res.json();
}

export async function updateLlmSettings(input: UpdateLlmSettingsInput): Promise<LlmSettings> {
  const res = await apiFetch('/api/settings/llm', {
    method: 'PUT',
    body: JSON.stringify(input),
  });
  return res.json();
}

export async function lintWiki(): Promise<{ issues: LintIssue[]; counts: { issues: number } }> {
  const res = await apiFetch('/api/lint');
  return res.json();
}

export async function applyLintFix(fix: { type: string; [key: string]: string }): Promise<{ detail: string; message?: string }> {
  const res = await apiFetch('/api/lint/fix', {
    method: 'POST',
    body: JSON.stringify(fix),
  });
  return res.json();
}

export async function query(
  question: string,
  onToken: (t: string) => void,
  onCitations: (c: Page[]) => void,
): Promise<void> {
  const csrf = csrfToken();
  const response = await fetch('/api/query', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
    },
    body: JSON.stringify({ question }),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(text || `HTTP ${response.status}`);
  }

  await parseSSEStream(response, (data) => {
    const event = data as { type: string; token?: string; citations?: Page[] };
    if (event.type === 'token' && event.token !== undefined) {
      onToken(event.token);
    } else if (event.type === 'citations' && event.citations) {
      onCitations(event.citations);
    }
  });
}
