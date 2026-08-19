import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import fs from 'node:fs';
import path from 'node:path';
import { AppProvider } from '../store';
import { ToastProvider } from '../components/ui/Toast';
import StreamSurface from './StreamSurface';

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    getActivity: vi.fn(async () => ({ items: [], next_before: null, pending_review: 0 })),
  };
});

describe('the stream is home', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens on the stream, not a dashboard', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8');

    expect(source).toContain('path="/" element={<StreamSurface />}');
    // The dashboard, the tool section and the workflow section are gone; their
    // URLs redirect rather than 404.
    expect(source).toContain('path="/review" element={<Navigate to="/entries?needs_review=1"');
    expect(source).toContain('path="/tools/*"');
    expect(source).not.toContain('<HomePage />');
  });

  it('renders a loading state before the feed arrives', () => {
    const html = renderToString(
      <StaticRouter location="/">
        <AppProvider>
          <ToastProvider>
            <StreamSurface />
          </ToastProvider>
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('Opening your vault');
  });
});

describe('user-facing copy', () => {
  const files = [
    'src/shell/AppShell.tsx',
    'src/surfaces/StreamSurface.tsx',
    'src/surfaces/EverythingSurface.tsx',
    'src/surfaces/SelfSurface.tsx',
    'src/surfaces/VisualizedSurface.tsx',
  ];

  it('uses sentence case for headings, not title case', () => {
    // Title-case labels from the previous design that must not come back.
    const titleCased = [
      'Knowledge Graph',
      'Memory Assets',
      'Vault Health',
      'Daily Note',
      'Vault Snapshot',
      'AI Workbench',
      'Review Queue',
      'Quick Capture',
      'Setup Status',
    ];

    for (const file of files) {
      const source = fs.readFileSync(path.resolve(file), 'utf8');
      for (const phrase of titleCased) {
        expect(source, `${file} should not use "${phrase}"`).not.toContain(phrase);
      }
    }
  });
});
