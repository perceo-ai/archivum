import { describe, expect, it } from 'vitest';
import { mergeFrontmatterProperties, parseFrontmatter } from './frontmatter';

describe('frontmatter document properties', () => {
  it('hides YAML frontmatter from the editable body', () => {
    expect(parseFrontmatter('---\ntitle: Old\ntags: [a]\n---\n\n# Body').body).toBe('# Body');
  });

  it('preserves frontmatter while updating title and tags', () => {
    const markdown = '---\ntitle: Old\ntype: project\ntags: [a]\n---\n\n# Body';

    expect(mergeFrontmatterProperties(markdown, 'Updated body', 'New Title', ['alpha', 'beta'])).toBe(
      '---\ntitle: New Title\ntags: [alpha, beta]\ntype: project\n---\n\nUpdated body',
    );
  });

  it('does not create frontmatter for plain markdown pages', () => {
    expect(mergeFrontmatterProperties('# Body', 'Body only', 'Title', ['tag'])).toBe('Body only');
  });
});
