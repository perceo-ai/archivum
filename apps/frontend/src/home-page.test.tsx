import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import fs from 'node:fs';
import path from 'node:path';
import { AppProvider } from './store';
import HomePage from './pages/HomePage';

describe('human-centered home surface', () => {
  it('renders person:self capture, context, review, and accepted memory sections', () => {
    const html = renderToString(
      <StaticRouter location="/">
        <AppProvider>
          <HomePage />
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('person:self');
    expect(html).toContain('What should Archivum remember?');
    expect(html).toContain('Librarian response');
    expect(html).toContain('Current active context');
    expect(html).toContain('Context explanations');
    expect(html).toContain('Staleness warnings');
    expect(html).toContain('Suggested updates');
    expect(html).toContain('Accepted memory');
  });

  it('keeps the root route on Home instead of redirecting into wiki pages', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8');

    expect(source).toContain("path=\"/\" element={");
    expect(source).toContain('<HomePage />');
    expect(source).not.toContain('pages.length > 0');
  });
});
