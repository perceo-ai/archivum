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

describe('apiFetch error handling', () => {
  it('throws with error body text when response is not ok', async () => {
    fetchMock.mockResolvedValueOnce(new Response('Not found', { status: 404 }));
    await expect(getPage('missing')).rejects.toThrow('Not found');
  });

  it('throws with HTTP status when body is empty', async () => {
    fetchMock.mockResolvedValueOnce(new Response('', { status: 500, statusText: 'Internal Server Error' }));
    await expect(getPage('oops')).rejects.toThrow('HTTP 500');
  });
});
