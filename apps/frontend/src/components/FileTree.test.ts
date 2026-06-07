import { describe, expect, it } from 'vitest';
import {
  makeVaultDragPayload,
  parseVaultDragPayload,
  vaultActionButtonLabel,
} from './FileTree';

describe('FileTree helpers', () => {
  it('uses a structured drag payload for vault pages and folders', () => {
    expect(parseVaultDragPayload(makeVaultDragPayload('page', 'projects/note'))).toEqual({
      type: 'page',
      path: 'projects/note',
    });
    expect(parseVaultDragPayload(makeVaultDragPayload('folder', 'projects'))).toEqual({
      type: 'folder',
      path: 'projects',
    });
  });

  it('ignores non-vault drag payloads', () => {
    expect(parseVaultDragPayload('page:projects/note')).toBeNull();
    expect(parseVaultDragPayload('')).toBeNull();
    expect(parseVaultDragPayload('{bad json')).toBeNull();
  });

  it('uses explicit action labels instead of generic apply', () => {
    expect(vaultActionButtonLabel('new-folder')).toBe('Create folder');
    expect(vaultActionButtonLabel('new-page')).toBe('Create page');
    expect(vaultActionButtonLabel('move-page')).toBe('Move');
    expect(vaultActionButtonLabel('delete-folder')).toBe('Delete');
  });
});
