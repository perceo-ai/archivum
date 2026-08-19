import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import fs from 'node:fs';
import path from 'node:path';
import { AppProvider } from '../store';
import { ToastProvider } from '../components/ui/Toast';
import { BrandMark, LOGO_SRC } from './BrandMark';
import LoginPage from '../pages/LoginPage';
import SetupPage from '../pages/SetupPage';

/**
 * The logo regressed once already: the redesign replaced the rail's image with
 * a lettermark and left the asset wired up only as a favicon. These assert both
 * halves — that the file ships, and that the surfaces actually reference it.
 */

describe('the brand mark', () => {
  it('ships the asset Vite copies into the build', () => {
    const asset = path.resolve('public', LOGO_SRC.replace(/^\//, ''));
    expect(fs.existsSync(asset), `${asset} must exist to be served`).toBe(true);
    expect(fs.statSync(asset).size).toBeGreaterThan(0);
  });

  it('renders the logo, not a lettermark', () => {
    const html = renderToString(<BrandMark />);
    expect(html).toContain(LOGO_SRC);
    expect(html).toContain('alt="Archivum"');
  });

  it('appears in the sidebar', () => {
    const source = fs.readFileSync(path.resolve('src/shell/AppShell.tsx'), 'utf8');
    expect(source).toContain('<BrandMark');
  });

  it('appears on the surfaces outside the app shell', () => {
    for (const page of ['/login', '/setup']) {
      const html = renderToString(
        <StaticRouter location={page}>
          <AppProvider>
            <ToastProvider>{page === '/login' ? <LoginPage /> : <SetupPage />}</ToastProvider>
          </AppProvider>
        </StaticRouter>,
      );
      expect(html, `${page} should show the logo`).toContain(LOGO_SRC);
    }
  });

  it('is also the favicon', () => {
    const html = fs.readFileSync(path.resolve('index.html'), 'utf8');
    expect(html).toContain(LOGO_SRC);
  });
});
