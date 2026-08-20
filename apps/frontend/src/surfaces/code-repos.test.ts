import { afterEach, describe, expect, it, vi } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const fetchMock = vi.fn();
vi.stubGlobal('fetch', fetchMock);
vi.stubGlobal('document', { cookie: '' });

afterEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('document', { cookie: '' });
});

function jsonResponse(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

const repo = {
  scope: 'repo:atlas',
  name: 'atlas',
  path: '/src/atlas',
  status: 'ready',
  files: 12,
  nodes: 240,
  edges: 610,
  pages: 8,
  error: null,
  indexed_at: '2026-08-20T00:00:00Z',
};

/**
 * Archivum is memory for someone who writes code, so repositories need the same
 * reach as everything else: registerable, listable, and visible in the graph.
 */
describe('the repository client', () => {
  it('lists what has been indexed', async () => {
    const { listRepos } = await import('../api');
    fetchMock.mockResolvedValueOnce(jsonResponse([repo]));

    const repos = await listRepos();

    expect(repos[0].nodes).toBe(240);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/repos');
  });

  it('registers a repository by path', async () => {
    const { registerRepo } = await import('../api');
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...repo, status: 'pending' }));

    const created = await registerRepo({ path: '/src/atlas' });

    // Indexing is queued, so the UI has to be able to show a pending state.
    expect(created.status).toBe('pending');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/repos');
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
  });

  it('can ask for a re-read of a repository it already knows', async () => {
    const { reindexRepo } = await import('../api');
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...repo, status: 'pending' }));

    await reindexRepo('atlas');

    expect(fetchMock.mock.calls[0][0]).toBe('/api/repos/atlas/reindex');
  });

  it('scopes the graph audit to a repository when asked', async () => {
    const { getGraphAudit } = await import('../api');
    fetchMock.mockResolvedValueOnce(jsonResponse({ scope: 'repo:atlas', node_count: 1 }));

    await getGraphAudit(10, 'repo:atlas');

    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/graph/audit?surprise_limit=10&scope=repo%3Aatlas',
    );
  });

  it('leaves the scope off for the ordinary vault audit', async () => {
    const { getGraphAudit } = await import('../api');
    fetchMock.mockResolvedValueOnce(jsonResponse({ scope: 'wiki:default' }));

    await getGraphAudit();

    expect(fetchMock.mock.calls[0][0]).toBe('/api/graph/audit?surprise_limit=10');
  });
});

describe('the settings page', () => {
  it('offers repository indexing', () => {
    const source = fs.readFileSync(path.resolve('src/pages/SettingsPage.tsx'), 'utf8');
    expect(source).toContain('CodeRepos');
  });
});

describe('the visualized surface', () => {
  it('can be pointed at an indexed repository', () => {
    const source = fs.readFileSync(
      path.resolve('src/surfaces/VisualizedSurface.tsx'),
      'utf8',
    );
    // Without a scope picker the code graph exists and nobody can look at it.
    expect(source).toContain('listRepos');
    expect(source).toMatch(/getGraphAudit\(\s*10\s*,\s*scope/);
  });
});

describe('drawing a repository graph', () => {
  const source = () =>
    fs.readFileSync(path.resolve('src/surfaces/VisualizedSurface.tsx'), 'utf8');

  it('names cluster members from the report it drew them from', () => {
    // Labels used to come from a second, unscoped call, so a repository graph
    // rendered rows of `repo_atlas_geo_haversine` instead of function names.
    expect(source()).toContain('node_labels');
    expect(source()).not.toMatch(/labelById[\s\S]{0,200}nodes\.map/);
  });

  it('puts the repository at the centre when you are looking at one', () => {
    // The centre is "you" for the vault. A repository is not you, so drawing
    // your initials in the middle of a call graph is just wrong.
    expect(source()).toContain('centreLabel');
    expect(source()).toContain('centreSubtitle');
  });

  it('links each cluster to the page that was written for it', () => {
    // Indexing writes code/<repo>/<cluster>.md — the picture should open it.
    expect(source()).toContain('code/');
  });
});
