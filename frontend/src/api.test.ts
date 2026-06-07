import { afterEach, describe, expect, it, vi } from 'vitest';
import { refreshSession } from './api';

const fetchMock = vi.fn();

vi.stubGlobal('fetch', fetchMock);
vi.stubGlobal('document', { cookie: '' });

afterEach(() => {
  fetchMock.mockReset();
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
