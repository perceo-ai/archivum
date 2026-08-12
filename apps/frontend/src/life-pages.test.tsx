import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { AppProvider } from './store';
import Layout from './components/Layout';
import DailyPage from './pages/DailyPage';
import WorkflowsPage from './pages/WorkflowsPage';
import ToolsPage from './pages/ToolsPage';
import SettingsPage from './pages/SettingsPage';
import { DEFAULT_FOLDER_PATHS, buildTree } from './components/FileTree';

describe('Life OS pages', () => {
  it('renders the daily note workflow', () => {
    const html = renderToString(
      <StaticRouter location="/daily">
        <DailyPage />
      </StaticRouter>,
    );

    expect(html).toContain('Open daily note');
  });

  it('adds grouped navigation to the app shell', () => {
    const html = renderToString(
      <StaticRouter location="/workflows/daily">
        <AppProvider>
          <Layout>
            <div>Body</div>
          </Layout>
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('Library');
    expect(html).toContain('Workflows');
    expect(html).toContain('Tools');
  });

  it('renders workflows shell entry points', () => {
    const html = renderToString(
      <StaticRouter location="/workflows/tasks">
        <WorkflowsPage />
      </StaticRouter>,
    );

    expect(html).toContain('Daily');
    expect(html).toContain('Projects');
    expect(html).toContain('Tasks');
  });

  it('uses page-focused workflow copy', () => {
    const html = renderToString(
      <StaticRouter location="/workflows/tasks">
        <WorkflowsPage />
      </StaticRouter>,
    );

    expect(html).toContain('Tasks');
    expect(html).toContain('Capture open loops and keep the next action visible.');
    expect(html).not.toContain('surface');
    expect(html).not.toContain('shell clutter');
  });

  it('renders tools shell entry points', () => {
    const html = renderToString(
      <StaticRouter location="/tools/graph">
        <ToolsPage />
      </StaticRouter>,
    );

    expect(html).toContain('Graph');
    expect(html).toContain('Ingest');
    expect(html).toContain('Settings');
  });

  it('uses page-focused tools copy', () => {
    const html = renderToString(
      <StaticRouter location="/tools/graph">
        <ToolsPage />
      </StaticRouter>,
    );

    expect(html).toContain('Knowledge Graph');
    expect(html).toContain('Explore entities, pages, and backlinks as a connected map.');
    expect(html).not.toContain('Utility surfaces');
    expect(html).not.toContain('cleaner tools workspace');
  });

  it('gives the knowledge graph a viewport-height workspace', () => {
    const html = renderToString(
      <StaticRouter location="/tools/graph">
        <ToolsPage />
      </StaticRouter>,
    );

    expect(html).toContain('page-frame h-full min-h-0 bg-transparent');
    expect(html).toContain('relative min-h-0 flex-1');
  });

  it('renders LLM provider settings', () => {
    const html = renderToString(
      <StaticRouter location="/tools/settings">
        <SettingsPage />
      </StaticRouter>,
    );

    expect(html).toContain('LLM Provider');
    expect(html).toContain('Loading LLM settings');
  });

  it('organizes root pages under Inbox instead of leaving loose root clutter', () => {
    const tree = buildTree(
      [
        { slug: 'loose-note', title: 'Loose Note', authored_by: 'user' },
        { slug: 'projects/archivum', title: 'Archivum', authored_by: 'agent' },
      ],
      [],
    );

    expect(tree.pages).toEqual([]);
    expect(tree.folders.map((folder) => folder.path).slice(0, DEFAULT_FOLDER_PATHS.length)).toEqual(
      [...DEFAULT_FOLDER_PATHS],
    );
    expect(tree.folders.find((folder) => folder.path === 'inbox')?.pages.map((page) => page.slug)).toEqual([
      'loose-note',
    ]);
    expect(tree.folders.find((folder) => folder.path === 'projects')?.pages.map((page) => page.slug)).toEqual([
      'projects/archivum',
    ]);
  });
});
