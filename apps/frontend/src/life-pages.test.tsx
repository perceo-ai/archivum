import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { AppProvider } from './store';
import Layout from './components/Layout';
import DailyPage from './pages/DailyPage';

describe('Life OS pages', () => {
  it('renders the daily note workflow', () => {
    const html = renderToString(
      <StaticRouter location="/daily">
        <DailyPage />
      </StaticRouter>,
    );

    expect(html).toContain('Open daily note');
  });

  it('adds Life OS navigation to the app shell', () => {
    const html = renderToString(
      <StaticRouter location="/daily">
        <AppProvider>
          <Layout>
            <div>Body</div>
          </Layout>
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('Daily');
    expect(html).toContain('Projects');
    expect(html).toContain('Tasks');
    expect(html).toContain('Decisions');
    expect(html).toContain('Activity');
  });
});
