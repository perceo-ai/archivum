import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import fs from 'node:fs';
import path from 'node:path';
import { AppProvider } from './store';
import HomePage from './pages/HomePage';
import { ToastProvider } from './components/ui/Toast';

describe('human-centered home surface', () => {
  it('renders a practical owner dashboard with quick actions and status', () => {
    const html = renderToString(
      <StaticRouter location="/">
        <AppProvider>
          <ToastProvider>
            <HomePage />
          </ToastProvider>
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('Today in Archivum');
    expect(html).toContain('Use AI to draft, query, organize, and save useful knowledge into the vault.');
    expect(html).toContain('AI Workbench');
    expect(html).toContain('Vault Snapshot');
    expect(html).toContain('Setup Status');
    expect(html).toContain('Quick Capture');
    expect(html).toContain('Review Queue');
    expect(html).toContain('Agent Memory');
    expect(html).not.toContain('person:self');
  });

  it('keeps the root route on Home instead of redirecting into wiki pages', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8');

    expect(source).toContain("path=\"/\" element={");
    expect(source).toContain('<HomePage />');
    expect(source).not.toContain('pages.length > 0');
  });
});
