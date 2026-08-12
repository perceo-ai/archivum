import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { ProvenanceDrawer } from './ProvenanceDrawer';

describe('ProvenanceDrawer', () => {
  it('renders citation method and confidence', () => {
    const html = renderToString(
      <ProvenanceDrawer
        open
        onClose={() => {}}
        citations={[{ source_id: 'page:alpha', chunk_id: 'page:alpha', span_start: 0, span_end: 5, quote: 'Alpha' }]}
        extractionMethod="INFERRED"
        confidence={0.72}
      />,
    );

    expect(html).toContain('INFERRED');
    expect(html).toContain('72%');
    expect(html).toContain('Alpha');
  });
});
