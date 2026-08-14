import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { AppProvider } from './store';
import ReviewPage from './pages/ReviewPage';
import ToolsPage from './pages/ToolsPage';
import LensPage from './pages/LensPage';

describe('review surface', () => {
  it('renders rich suggested update card fields', () => {
    const html = renderToString(
      <StaticRouter location="/review">
        <AppProvider>
          <ReviewPage />
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('Review');
    expect(html).toContain('Why it matters');
    expect(html).toContain('Scope');
    expect(html).toContain('Durability');
    expect(html).toContain('Agent visibility');
    expect(html).toContain('Conflicts');
    expect(html).toContain('Redundancy');
  });

  it('does not hide review under tools navigation', () => {
    const html = renderToString(
      <StaticRouter location="/tools/graph">
        <ToolsPage />
      </StaticRouter>,
    );

    expect(html).not.toContain('Review updates');
  });
});

describe('human-first graph lenses', () => {
  it('renders topic people repo and source lenses', () => {
    for (const [location, lens, title] of [
      ['/topics', 'topics', 'Topics'],
      ['/people', 'people', 'People'],
      ['/repos', 'repos', 'Repos'],
      ['/sources', 'sources', 'Sources'],
    ] as const) {
      const html = renderToString(
        <StaticRouter location={location}>
          <LensPage lens={lens} />
        </StaticRouter>,
      );

      expect(html).toContain(title);
      expect(html).toContain('person:self lens');
    }
  });
});
