import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { AppProvider } from './store';
import Layout from './components/Layout';
import DailyPage from './pages/DailyPage';
import WorkflowsPage from './pages/WorkflowsPage';
import ToolsPage from './pages/ToolsPage';
import SettingsPage from './pages/SettingsPage';

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

  it('renders LLM provider settings', () => {
    const html = renderToString(
      <StaticRouter location="/tools/settings">
        <SettingsPage />
      </StaticRouter>,
    );

    expect(html).toContain('LLM Provider');
    expect(html).toContain('Loading LLM settings');
  });
});
