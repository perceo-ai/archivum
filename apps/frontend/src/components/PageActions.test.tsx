import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import PageActions from './PageActions';

describe('PageActions', () => {
  it('keeps the document action surface compact', () => {
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

    expect(html).toContain('Share page');
    expect(html).toContain('More page actions');
    expect(html).not.toContain('Export page as HTML');
    expect(html).not.toContain('Export page as PDF');
  });
});
