import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { ToastProvider } from '../components/ui/Toast';
import ReindexControl, { describeDegraded } from './ReindexControl';

/**
 * The vault is editable by hand, so reindexing has to be a thing you can see.
 * These render server-side, so effects and clicks do not run; the naming
 * logic is the part with real behaviour, so it is tested directly.
 */

describe('the reindex control', () => {
  it('offers to re-read the page from disk', () => {
    const html = renderToString(
      <ToastProvider>
        <ReindexControl slug="topics/retrieval" />
      </ToastProvider>,
    );
    expect(html).toContain('Re-read this page from disk');
  });

  it('says nothing about degradation until something has degraded', () => {
    const html = renderToString(
      <ToastProvider>
        <ReindexControl slug="topics/retrieval" />
      </ToastProvider>,
    );
    expect(html).not.toContain('out of date');
  });
});

describe('naming what fell behind', () => {
  it('translates backend projection keys into what the user lost', () => {
    expect(describeDegraded(['search'])).toBe('Search');
    expect(describeDegraded(['graph.node'])).toBe('The graph');
  });

  it('collapses the several graph projections into one name', () => {
    // The backend reports graph.node, graph.edges and graph.knowledge
    // separately. Listing all three would describe the implementation rather
    // than the consequence, which is that the graph is stale.
    expect(describeDegraded(['graph.node', 'graph.edges', 'graph.knowledge'])).toBe(
      'The graph',
    );
  });

  it('reads as one phrase when both fell behind', () => {
    // Not "Search and The graph": only the first name is capitalised, because
    // this is a sentence fragment, not a list of labels.
    expect(describeDegraded(['search', 'graph.edges'])).toBe('Search and the graph');
  });
});
