import { describe, expect, it } from 'vitest';
import { addTag, removeTag } from './wikiMetadata';

describe('wiki metadata tag editing', () => {
  it('adds trimmed unique tags and removes tags without comma-separated drafts', () => {
    expect(addTag(['research'], '  graph notes  ')).toEqual(['research', 'graph notes']);
    expect(addTag(['research'], 'research')).toEqual(['research']);
    expect(removeTag(['research', 'graph notes'], 'research')).toEqual(['graph notes']);
  });
});
