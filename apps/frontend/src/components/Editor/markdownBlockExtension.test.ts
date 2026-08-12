import { describe, expect, it } from 'vitest';
import { classifyMarkdownLine } from './markdownBlockExtension';

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
