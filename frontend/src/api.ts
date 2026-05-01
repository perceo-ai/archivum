import type { Page, SearchResult, GraphNode, GraphEdge, IngestProgress } from './types';

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

export async function login(password: string): Promise<void> {
  await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
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

export async function getBacklinks(slug: string): Promise<Page[]> {
  const res = await apiFetch(`/api/pages/${encodeSlugPath(slug)}/backlinks`);
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
  onProgress: (p: IngestProgress) => void,
): Promise<void> {
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

  await parseSSEStream(response, (data) => onProgress(data as IngestProgress));
}

export async function ingestUrl(
  url: string,
  onProgress: (p: IngestProgress) => void,
): Promise<void> {
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

  await parseSSEStream(response, (data) => onProgress(data as IngestProgress));
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
