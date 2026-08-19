import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { AppProvider, reducer } from './store';
import Layout from './components/Layout';
import fs from 'node:fs';
import path from 'node:path';

describe('app shell layout', () => {
  it('defaults the vault sidebar open', () => {
    const state = reducer(undefined, { type: 'SET_AUTH', value: true });

    expect(state.leftOpen).toBe(true);
  });

  it('tracks quick search as shell state', () => {
    const opened = reducer(undefined, { type: 'SET_QUICK_SEARCH_OPEN', open: true });
    const closed = reducer(opened, { type: 'SET_QUICK_SEARCH_OPEN', open: false });

    expect(opened.quickSearchOpen).toBe(true);
    expect(closed.quickSearchOpen).toBe(false);
  });

  it('renders a full-width Perceo shell without nested surface panels', () => {
    const html = renderToString(
      <StaticRouter location="/wiki/home">
        <AppProvider>
          <Layout>
            <div>Body</div>
          </Layout>
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('perceo-shell');
    expect(html).not.toContain('grid-lines');
    expect(html).toContain('vault-sidebar');
    expect(html).not.toContain('max-w-6xl');
    expect(html).not.toContain('rounded-[32px]');
  });

  it('keeps the library shell grid off wiki editing pages only', () => {
    const html = renderToString(
      <StaticRouter location="/library">
        <AppProvider>
          <Layout>
            <div>Body</div>
          </Layout>
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('grid-lines');
  });

  it('uses charcoal color and typography tokens', () => {
    const css = fs.readFileSync(path.resolve('src/index.css'), 'utf8');

    expect(css).toContain('--background: 0 0% 9%');
    expect(css).toContain('--primary: 257 90% 66%');
    expect(css).toContain('--accent: 257 90% 66%');
    expect(css).toContain('Instrument Sans');
    expect(css).toContain('Playfair Display');
    expect(css).toContain('.grid-lines');
  });
});
