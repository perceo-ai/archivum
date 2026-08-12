import { describe, expect, it } from 'vitest';
import {
  applySlashCommandToLine,
  getEnterInsertionForLine,
  moveMarkdownBlockByOffset,
  moveMarkdownBlockInText,
  toggleTaskLine,
} from './slashCommands';

describe('applySlashCommandToLine', () => {
  it('turns slash query text into markdown-backed blocks', () => {
    expect(applySlashCommandToLine('/h1 Roadmap', 'heading-1')).toBe('# Roadmap');
    expect(applySlashCommandToLine('/todo Ship polish', 'todo')).toBe('- [ ] Ship polish');
    expect(applySlashCommandToLine('/divider', 'divider')).toBe('---');
  });
});

describe('moveMarkdownBlockByOffset', () => {
  it('moves the current markdown block one neighboring block at a time', () => {
    expect(moveMarkdownBlockByOffset('Alpha\nBravo\nCharlie', 2, -1)).toEqual({
      text: 'Bravo\nAlpha\nCharlie',
      lineNumber: 1,
    });
    expect(moveMarkdownBlockByOffset('Alpha\n- Parent\n  child\nCharlie', 2, 1)).toEqual({
      text: 'Alpha\nCharlie\n- Parent\n  child',
      lineNumber: 3,
    });
  });
});

describe('moveMarkdownBlockInText', () => {
  it('moves a dragged markdown block before the drop target block', () => {
    expect(moveMarkdownBlockInText('Alpha\n- Parent\n  continuation\nCharlie\nDelta', 2, 5)).toBe(
      'Alpha\nCharlie\n- Parent\n  continuation\nDelta',
    );
    expect(moveMarkdownBlockInText('Alpha\n```js\nconst x = 1\n```\nOmega', 2, 1)).toBe(
      '```js\nconst x = 1\n```\nAlpha\nOmega',
    );
  });
});

describe('getEnterInsertionForLine', () => {
  it('continues and exits markdown list-like blocks', () => {
    expect(getEnterInsertionForLine('- Write docs')).toEqual({ replaceLine: null, insertion: '\n- ' });
    expect(getEnterInsertionForLine('- [ ] Write tests')).toEqual({ replaceLine: null, insertion: '\n- [ ] ' });
    expect(getEnterInsertionForLine('> Quote')).toEqual({ replaceLine: null, insertion: '\n> ' });
    expect(getEnterInsertionForLine('- ')).toEqual({ replaceLine: '', insertion: '\n' });
  });
});

describe('toggleTaskLine', () => {
  it('toggles markdown task checkboxes without changing the task text', () => {
    expect(toggleTaskLine('- [ ] Ship polish')).toBe('- [x] Ship polish');
    expect(toggleTaskLine('- [x] Ship polish')).toBe('- [ ] Ship polish');
  });
});
