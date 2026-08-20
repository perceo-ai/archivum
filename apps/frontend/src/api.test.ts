import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  refreshSession,
  login,
  logout,
  listPages,
  getPage,
  createPage,
  updatePage,
  deletePage,
  duplicatePage,
  listFolders,
  createFolder,
  moveFolder,
  deleteFolder,
  movePage,
  getBacklinks,
  search,
  getGraph,
  ensureDailyNote,
  getLlmSettings,
  getAudioSupport,
  getMcpSettings,
  installAudioSupport,
  updateLlmSettings,
  listSuggestions,
  listPageSuggestions,
  acceptSuggestion,
  rejectSuggestion,
  reviewSuggestion,
  expireSuggestions,
  listMemoryScopes,
  upsertMemoryScope,
} from './api';
import type { Page, SearchResult, GraphNode, GraphEdge } from './types';

const fetchMock = vi.fn();

vi.stubGlobal('fetch', fetchMock);
vi.stubGlobal('document', { cookie: '' });

afterEach(() => {
  fetchMock.mockReset();
  // Reset cookie to empty after each test
  vi.stubGlobal('document', { cookie: '' });
});

const makePage = (overrides: Partial<Page> = {}): Page => ({
  slug: 'test-page',
  title: 'Test Page',
  content: 'Some content',
  tags: [],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  authored_by: 'agent',
  ...overrides,
});

const apiJsonResponse = (body: unknown) => new Response(JSON.stringify(body), {
  status: 200,
  headers: { 'Content-Type': 'application/json' },
});

describe('refreshSession', () => {
  it('posts to the refresh endpoint using persisted cookies', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ username: 'admin', role: 'owner', wiki_id: 'default' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(refreshSession()).resolves.toEqual({
      username: 'admin',
      role: 'owner',
      wiki_id: 'default',
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/refresh', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
  });
});

describe('login', () => {
  it('posts credentials to /api/auth/login', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 200 }));

    await expect(login('secret')).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
    const callArgs = fetchMock.mock.calls[0][1];
    expect(JSON.parse(callArgs.body)).toEqual({ password: 'secret' });
  });

  it('throws on non-ok response', async () => {
    fetchMock.mockResolvedValueOnce(new Response('Unauthorized', { status: 401 }));
    await expect(login('wrong')).rejects.toThrow('Unauthorized');
  });
});

describe('logout', () => {
  it('posts to /api/auth/logout', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 200 }));

    await expect(logout()).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
  });
});

describe('listPages', () => {
  it('fetches GET /api/pages and returns array', async () => {
    const pages = [makePage({ slug: 'one' }), makePage({ slug: 'two' })];
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(pages),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(listPages()).resolves.toEqual(pages);

    expect(fetchMock).toHaveBeenCalledWith('/api/pages', expect.objectContaining({
      credentials: 'include',
    }));
    const callArgs = fetchMock.mock.calls[0][1];
    expect(callArgs.method).toBeUndefined();
  });
});

describe('getPage', () => {
  it('fetches GET /api/pages/:slug', async () => {
    const page = makePage({ slug: 'hello-world' });
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(page),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(getPage('hello-world')).resolves.toEqual(page);

    expect(fetchMock).toHaveBeenCalledWith('/api/pages/hello-world', expect.objectContaining({
      credentials: 'include',
    }));
  });

  it('encodes slug path segments', async () => {
    const page = makePage({ slug: 'section/sub page' });
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(page),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await getPage('section/sub page');

    expect(fetchMock).toHaveBeenCalledWith('/api/pages/section/sub%20page', expect.anything());
  });
});

describe('createPage', () => {
  it('posts to /api/pages with title/content/tags', async () => {
    const page = makePage({ slug: 'new-page', title: 'New Page' });
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(page),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(createPage({ title: 'New Page', content: 'Hello', tags: ['tag1'] })).resolves.toEqual(page);

    expect(fetchMock).toHaveBeenCalledWith('/api/pages', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
    const callArgs = fetchMock.mock.calls[0][1];
    expect(JSON.parse(callArgs.body)).toEqual({
      title: 'New Page',
      content: 'Hello',
      tags: ['tag1'],
      slug: undefined,
    });
  });

  it('sends CSRF token when cookie present', async () => {
    vi.stubGlobal('document', { cookie: 'csrf_token=test-csrf-token' });

    const page = makePage();
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(page),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await createPage({ title: 'Page' });

    expect(fetchMock).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
      headers: expect.objectContaining({ 'X-CSRF-Token': 'test-csrf-token' }),
    }));
  });
});

describe('updatePage', () => {
  it('puts to /api/pages/:slug', async () => {
    const page = makePage({ title: 'Updated' });
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(page),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(updatePage('test-page', { title: 'Updated' })).resolves.toEqual(page);

    expect(fetchMock).toHaveBeenCalledWith('/api/pages/test-page', expect.objectContaining({
      method: 'PUT',
      credentials: 'include',
    }));
    const callArgs = fetchMock.mock.calls[0][1];
    expect(JSON.parse(callArgs.body)).toEqual({ title: 'Updated' });
  });
});

describe('llm settings api', () => {
  it('fetches masked LLM settings', async () => {
    const settings = {
      llm_extraction_provider: 'ollama',
      llm_synthesis_provider: 'ollama',
      llm_model: 'model-a',
      llm_synthesis_model: 'model-b',
      ollama_base_url: 'https://ollama.example.com/v1',
      ollama_api_key_configured: true,
      ollama_api_key_masked: 'sk-...test',
    };
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(settings),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(getLlmSettings()).resolves.toEqual(settings);
    expect(fetchMock).toHaveBeenCalledWith('/api/settings/llm', expect.objectContaining({
      credentials: 'include',
    }));
  });

  it('updates LLM settings with CSRF token', async () => {
    vi.stubGlobal('document', { cookie: 'csrf_token=test-csrf-token' });
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({
        llm_extraction_provider: 'ollama',
        llm_synthesis_provider: 'ollama',
        llm_model: 'model-a',
        llm_synthesis_model: 'model-b',
        ollama_base_url: 'https://ollama.example.com/v1',
        ollama_api_key_configured: true,
        ollama_api_key_masked: 'sk-...test',
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await updateLlmSettings({
      llm_extraction_provider: 'ollama',
      llm_synthesis_provider: 'ollama',
      llm_model: 'model-a',
      llm_synthesis_model: 'model-b',
      ollama_base_url: 'https://ollama.example.com/v1',
      ollama_api_key: 'secret',
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/settings/llm', expect.objectContaining({
      method: 'PUT',
      credentials: 'include',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'test-csrf-token' }),
    }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      llm_extraction_provider: 'ollama',
      llm_synthesis_provider: 'ollama',
      llm_model: 'model-a',
      llm_synthesis_model: 'model-b',
      ollama_base_url: 'https://ollama.example.com/v1',
      ollama_api_key: 'secret',
    });
  });
});

describe('audio support api', () => {
  it('fetches current audio support status', async () => {
    const status = {
      available: false,
      dependencies: { openai_whisper: false, ffmpeg: true },
      missing: ['openai-whisper'],
      notes: [],
    };
    fetchMock.mockResolvedValueOnce(apiJsonResponse(status));

    await expect(getAudioSupport()).resolves.toEqual(status);
    expect(fetchMock).toHaveBeenCalledWith('/api/audio-support', expect.objectContaining({
      credentials: 'include',
    }));
  });

  it('installs audio support with CSRF protection', async () => {
    vi.stubGlobal('document', { cookie: 'csrf_token=audio-csrf' });
    const result = {
      ok: true,
      actions: [{ name: 'openai-whisper', status: 'installed', detail: 'Installed' }],
      status: {
        available: true,
        audio_available: true,
        video_available: true,
        dependencies: { openai_whisper: true, ffmpeg: true },
        missing: [],
        notes: [],
      },
    };
    fetchMock.mockResolvedValueOnce(apiJsonResponse(result));

    await expect(installAudioSupport()).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith('/api/audio-support/install', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'audio-csrf' }),
    }));
  });
});

describe('MCP settings api', () => {
  it('fetches MCP client settings', async () => {
    const settings = {
      endpoint: 'http://localhost:8001/sse',
      auth_required: true,
      api_key_configured: true,
      client_config: {
        mcpServers: {
          archivum: {
            url: 'http://localhost:8001/sse',
            headers: { Authorization: 'Bearer <MCP_API_KEY>' },
          },
        },
      },
    };
    fetchMock.mockResolvedValueOnce(apiJsonResponse(settings));

    await expect(getMcpSettings()).resolves.toEqual(settings);
    expect(fetchMock).toHaveBeenCalledWith('/api/settings/mcp', expect.objectContaining({
      credentials: 'include',
    }));
  });
});

describe('deletePage', () => {
  it('sends DELETE to /api/pages/:slug', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await expect(deletePage('test-page')).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledWith('/api/pages/test-page', expect.objectContaining({
      method: 'DELETE',
      credentials: 'include',
    }));
  });
});

describe('folders api', () => {
  it('fetches folders', async () => {
    const folders = [{ path: 'projects', name: 'projects', created_at: '2026-01-01', updated_at: '2026-01-01' }];
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(folders),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(listFolders()).resolves.toEqual(folders);

    expect(fetchMock).toHaveBeenCalledWith('/api/folders', expect.objectContaining({
      credentials: 'include',
    }));
  });

  it('creates folders', async () => {
    const folder = { path: 'projects', name: 'projects', created_at: '2026-01-01', updated_at: '2026-01-01' };
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(folder),
      { status: 201, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(createFolder({ path: 'projects' })).resolves.toEqual(folder);

    expect(fetchMock).toHaveBeenCalledWith('/api/folders', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ path: 'projects' });
  });

  it('moves folders with recursive intent', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ path: 'archive/projects', pages: 2, folders: 1 }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(moveFolder('projects', { new_path: 'archive/projects', recursive: true })).resolves.toEqual({
      path: 'archive/projects',
      pages: 2,
      folders: 1,
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/folders/projects', expect.objectContaining({
      method: 'PATCH',
      credentials: 'include',
    }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      new_path: 'archive/projects',
      recursive: true,
    });
  });

  it('deletes folders with recursive intent', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ path: 'projects', pages: 2, folders: 1 }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(deleteFolder('projects', { recursive: true })).resolves.toEqual({
      path: 'projects',
      pages: 2,
      folders: 1,
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/folders/projects?recursive=true', expect.objectContaining({
      method: 'DELETE',
      credentials: 'include',
    }));
  });
});

describe('page move helpers', () => {
  it('moves a page to a new slug', async () => {
    const page = makePage({ slug: 'archive/note' });
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(page),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(movePage('projects/note', { new_slug: 'archive/note' })).resolves.toEqual(page);

    expect(fetchMock).toHaveBeenCalledWith('/api/pages/projects/note/move', expect.objectContaining({
      method: 'PATCH',
      credentials: 'include',
    }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ new_slug: 'archive/note' });
  });

  it('duplicates a page to a new slug', async () => {
    const page = makePage({ slug: 'projects/note-copy' });
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(page),
      { status: 201, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(duplicatePage('projects/note', { new_slug: 'projects/note-copy', title: 'Note copy' })).resolves.toEqual(page);

    expect(fetchMock).toHaveBeenCalledWith('/api/pages/projects/note/duplicate', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      new_slug: 'projects/note-copy',
      title: 'Note copy',
    });
  });
});

describe('getBacklinks', () => {
  it('fetches backlinks for a slug', async () => {
    const pages = [makePage({ slug: 'referrer' })];
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(pages),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(getBacklinks('target-page')).resolves.toEqual(pages);

    expect(fetchMock).toHaveBeenCalledWith('/api/pages/target-page/backlinks', expect.objectContaining({
      credentials: 'include',
    }));
  });
});

describe('suggestions api', () => {
  const suggestion = {
    id: 'suggestion:one',
    target_id: 'page:default:target-page',
    suggestion_type: 'append_section',
    proposed_markdown: '## Suggested',
    proposed_objects: [],
    citations: [],
    proposed_scopes: ['person:self'],
    scores: { future_utility: 0.9 },
    duplicates: [],
    conflicts: ['memory:old'],
    retention_tier: 'candidate',
    agent_visibility: 'review_required',
    rationale: 'Useful later.',
    estimated_durability: 'durable',
    expires_at: null,
    status: 'pending' as const,
  };

  it('lists wiki suggestions', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify([suggestion]),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(listSuggestions()).resolves.toEqual([suggestion]);

    expect(fetchMock).toHaveBeenCalledWith('/api/suggestions', expect.objectContaining({
      credentials: 'include',
    }));
  });

  it('lists page suggestions with encoded page slug', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify([suggestion]),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(listPageSuggestions('folder/target page')).resolves.toEqual([suggestion]);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/suggestions?page_slug=folder%2Ftarget%20page',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('accepts suggestions with CSRF protection', async () => {
    vi.stubGlobal('document', { cookie: 'csrf_token=test-csrf-token' });
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ ...suggestion, status: 'accepted' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(acceptSuggestion('suggestion:one')).resolves.toEqual({ ...suggestion, status: 'accepted' });

    expect(fetchMock).toHaveBeenCalledWith('/api/suggestions/suggestion%3Aone/accept', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'test-csrf-token' }),
    }));
  });

  it('rejects suggestions', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ ...suggestion, status: 'rejected' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(rejectSuggestion('suggestion:one')).resolves.toEqual({ ...suggestion, status: 'rejected' });

    expect(fetchMock).toHaveBeenCalledWith('/api/suggestions/suggestion%3Aone/reject', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
  });

  it('sends review actions for merge and lifecycle decisions', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ ...suggestion, status: 'merged' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(reviewSuggestion('suggestion:one', 'merge')).resolves.toEqual({
      ...suggestion,
      status: 'merged',
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/suggestions/suggestion%3Aone/review', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      body: JSON.stringify({ action: 'merge' }),
    }));
  });

  it('sends destination payloads for scoped review actions', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ ...suggestion, status: 'scope_changed' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(reviewSuggestion('suggestion:one', 'change_scope', {
      asset_id: 'memory:target',
      scope: 'project:archivum',
    })).resolves.toEqual({
      ...suggestion,
      status: 'scope_changed',
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/suggestions/suggestion%3Aone/review', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      body: JSON.stringify({
        action: 'change_scope',
        asset_id: 'memory:target',
        scope: 'project:archivum',
      }),
    }));
  });

  it('expires due pending suggestions', async () => {
    fetchMock.mockResolvedValueOnce(apiJsonResponse([{ ...suggestion, status: 'expired' }]));

    await expect(expireSuggestions('2026-08-13T00:00:00+00:00')).resolves.toEqual([
      { ...suggestion, status: 'expired' },
    ]);

    expect(fetchMock).toHaveBeenCalledWith('/api/suggestions/expire', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ now: '2026-08-13T00:00:00+00:00' }),
    }));
  });
});

describe('memory scopes api', () => {
  const scope = {
    id: 'topic:clean-memory',
    wiki_id: 'default',
    scope_type: 'topic' as const,
    name: 'Clean memory',
    parent_scope_id: 'person:self',
    budget_tokens: 3000,
    budget_items: 12,
    retention_policy: { candidate_ttl_days: 14 },
  };

  it('lists memory scopes with optional type filter', async () => {
    fetchMock.mockResolvedValueOnce(apiJsonResponse([scope]));

    await expect(listMemoryScopes('topic')).resolves.toEqual([scope]);

    expect(fetchMock).toHaveBeenCalledWith('/api/memory/scopes?scope_type=topic', expect.objectContaining({
      credentials: 'include',
    }));
  });

  it('upserts a memory scope with CSRF protection', async () => {
    vi.stubGlobal('document', { cookie: 'csrf_token=scope-csrf' });
    fetchMock.mockResolvedValueOnce(apiJsonResponse(scope));

    await expect(upsertMemoryScope(scope)).resolves.toEqual(scope);

    expect(fetchMock).toHaveBeenCalledWith('/api/memory/scopes', expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'scope-csrf' }),
      body: JSON.stringify(scope),
    }));
  });
});

describe('capture and distillation api', () => {
  it('captures a typed conversation with CSRF protection', async () => {
    vi.stubGlobal('document', { cookie: 'csrf_token=csrf-123' });
    fetchMock.mockResolvedValueOnce(apiJsonResponse({
      source_id: 'source:capture:one',
      content_hash: 'abc',
      version: 1,
      document_id: 'doc:one',
      chunk_count: 2,
      deduplicated: false,
    }));

    const { captureConversation } = await import('./api');

    await expect(captureConversation({
      session_id: 'home-capture',
      interface: 'archivum_home',
      scope: 'person:self',
      turns: [{ role: 'user', text: 'Remember this.' }],
    })).resolves.toMatchObject({ source_id: 'source:capture:one' });

    expect(fetchMock).toHaveBeenCalledWith('/api/sources/capture', expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-123' }),
      body: JSON.stringify({
        session_id: 'home-capture',
        interface: 'archivum_home',
        started_at: '',
        scope: 'person:self',
        origin_uri: '',
        turns: [{ role: 'user', text: 'Remember this.', ts: '', tool_calls: [] }],
      }),
    }));
  });

  it('distills captured sources without forcing markdown page writes', async () => {
    fetchMock.mockResolvedValueOnce(apiJsonResponse({
      source_id: 'source:capture:one',
      session_id: 'home-capture',
      scope: 'person:self',
      atoms_total: 1,
      atoms_accepted: 0,
      atoms_pending_review: 1,
      asset_ids: [],
      scenario_id: null,
      persona_updated: false,
      skill_id: null,
      skill_reason: null,
      pages_written: [],
    }));

    const { distillSource } = await import('./api');

    await expect(distillSource({
      source_id: 'source:capture:one',
      scenario_key: 'home',
      write_pages: false,
    })).resolves.toMatchObject({ atoms_pending_review: 1 });

    expect(fetchMock).toHaveBeenCalledWith('/api/memory/distill', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        source_id: 'source:capture:one',
        scenario_key: 'home',
        threshold: undefined,
        write_pages: false,
      }),
    }));
  });
});

describe('search', () => {
  it('fetches /api/search?q=...', async () => {
    const results: SearchResult[] = [
      { slug: 'result', title: 'Result', excerpt: 'An excerpt', score: 0.9 },
    ];
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(results),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(search('hello world')).resolves.toEqual(results);

    expect(fetchMock).toHaveBeenCalledWith('/api/search?q=hello%20world', expect.objectContaining({
      credentials: 'include',
    }));
  });
});

describe('getGraph', () => {
  it('fetches /api/graph', async () => {
    const nodes: GraphNode[] = [{ id: 'p1', label: 'Page One', type: 'page' }];
    const edges: GraphEdge[] = [{ from: 'p1', to: 'p2', label: 'links' }];
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ nodes, edges }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(getGraph()).resolves.toEqual({ nodes, edges });

    expect(fetchMock).toHaveBeenCalledWith('/api/graph', expect.objectContaining({
      credentials: 'include',
    }));
  });
});

describe('life os api', () => {
  it('opens or creates a daily note', async () => {
    const page = makePage({ slug: 'daily-2026-06-21' });
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify(page),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(ensureDailyNote('2026-06-21')).resolves.toEqual(page);

    expect(fetchMock).toHaveBeenCalledWith('/api/life/daily', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ date: '2026-06-21' });
  });


});

describe('apiFetch error handling', () => {
  it('throws with error body text when response is not ok', async () => {
    fetchMock.mockResolvedValueOnce(new Response('Not found', { status: 404 }));
    await expect(getPage('missing')).rejects.toThrow('Not found');
  });

  it('throws with HTTP status when body is empty', async () => {
    fetchMock.mockResolvedValueOnce(new Response('', { status: 500, statusText: 'Internal Server Error' }));
    await expect(getPage('oops')).rejects.toThrow('Internal Server Error');
  });

  it('throws readable nested JSON errors', async () => {
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: { detail: 'ANTHROPIC_API_KEY not configured', code: 'missing_api_key' } }),
      { status: 400, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(getPage('oops')).rejects.toThrow('ANTHROPIC_API_KEY not configured');
  });
});
