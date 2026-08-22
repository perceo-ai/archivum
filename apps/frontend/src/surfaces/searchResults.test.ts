import { describe, expect, it } from 'vitest';
import { searchResults } from './searchResults';
import type { Entry, VaultHit } from '../api';

const entry = (slug: string, title: string): Entry => ({
  id: `page:${slug}`,
  kind: 'note',
  title,
  slug,
  folder: '',
  updated_at: '2026-08-22',
  created_at: '2026-08-22',
  actor: 'you',
  needs_review: false,
  tags: [],
  detail: '',
});

const hit = (slug: string, excerpt = ''): VaultHit => ({
  slug,
  title: slug,
  excerpt,
  score: 1,
});

describe('searchResults', () => {
  it('keeps the order the engine ranked them in', () => {
    const all = [entry('b', 'B'), entry('a', 'A')];
    expect(searchResults(all, [hit('a'), hit('b')]).map((e) => e.slug)).toEqual(['a', 'b']);
  });

  it('shows a hit that is not in the loaded page of entries', () => {
    // The entries list is capped and facet-filtered; search covers the vault.
    // Intersecting them silently dropped results the engine ranked first.
    const results = searchResults([], [hit('archive/old-note')]);
    expect(results.map((e) => e.slug)).toEqual(['archive/old-note']);
    expect(results[0].folder).toBe('archive');
  });

  it('shows the excerpt, which is why the result matched', () => {
    const results = searchResults([entry('a', 'A')], [hit('a', 'because of this line')]);
    expect(results[0].detail).toBe('because of this line');
  });

  it('does not repeat a slug the engine returned twice', () => {
    expect(searchResults([], [hit('a'), hit('a')])).toHaveLength(1);
  });

  it('returns nothing when the engine found nothing', () => {
    // With a relevance floor, "no matches" is now a real answer and must not
    // fall back to showing the whole list.
    expect(searchResults([entry('a', 'A')], [])).toEqual([]);
  });
});
