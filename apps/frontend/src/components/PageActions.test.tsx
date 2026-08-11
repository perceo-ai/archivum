import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import PageActions from './PageActions';

describe('PageActions', () => {
  it('keeps smoke-critical page actions visible', () => {
    const html = renderToString(
      <PageActions
        slug="release-notes"
        disabled={false}
        shareLoading={false}
        onSave={vi.fn()}
        onShare={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(html).toContain('Save');
    expect(html).toContain('Share page');
    expect(html).toContain('Export page as HTML');
    expect(html).toContain('Export page as PDF');
  });
});
