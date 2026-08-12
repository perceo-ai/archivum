import { describe, expect, it } from 'vitest';
import { matchPageForLinkQuery } from './wikilinkExtension';
import type { Page } from '../../types';

const page = (slug: string, title: string): Page => ({
  slug,
  title,
  content: '',
  tags: [],
  authored_by: 'user',
  created_at: '2026-08-12T00:00:00Z',
  updated_at: '2026-08-12T00:00:00Z',
});

describe('matchPageForLinkQuery', () => {
  it('scores exact, contains, and fuzzy page link matches', () => {
    expect(matchPageForLinkQuery(page('areas/archive-system', 'Archive System'), 'archive')).toBeGreaterThan(0);
    expect(matchPageForLinkQuery(page('people/ada-lovelace', 'Ada Lovelace'), 'al')).toBeGreaterThan(0);
    expect(matchPageForLinkQuery(page('daily/2026-08-12', 'Daily Note'), 'zzz')).toBe(0);
  });
});
