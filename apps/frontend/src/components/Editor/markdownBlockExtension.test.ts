import { describe, expect, it } from 'vitest';
import { classifyMarkdownLine, findInlineMarkdownMarks } from './markdownBlockExtension';

describe('classifyMarkdownLine', () => {
  it('identifies markdown blocks that should receive document-style editing treatments', () => {
    expect(classifyMarkdownLine('# Roadmap')).toMatchObject({
      kind: 'heading-1',
      marker: { from: 0, to: 2, label: '' },
    });
    expect(classifyMarkdownLine('- [x] Ship editor polish')).toMatchObject({
      kind: 'task-done',
      marker: { from: 0, to: 6, label: '☑' },
    });
    expect(classifyMarkdownLine('> Keep context visible')).toMatchObject({
      kind: 'quote',
      marker: { from: 0, to: 2, label: '' },
    });
    expect(classifyMarkdownLine('---')).toMatchObject({
      kind: 'thematic-break',
      marker: { from: 0, to: 3, label: '' },
    });
  });
});

describe('findInlineMarkdownMarks', () => {
  it('finds inline markdown delimiters that should be hidden in visual editing', () => {
    expect(findInlineMarkdownMarks('This is **bold**, *emphasis*, and `code`.')).toEqual([
      { from: 8, to: 10, kind: 'strong-marker' },
      { from: 14, to: 16, kind: 'strong-marker' },
      { from: 18, to: 19, kind: 'emphasis-marker' },
      { from: 27, to: 28, kind: 'emphasis-marker' },
      { from: 34, to: 35, kind: 'code-marker' },
      { from: 39, to: 40, kind: 'code-marker' },
    ]);
  });
});
