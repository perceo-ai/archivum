import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { AppProvider } from '../store';
import { ToastProvider } from '../components/ui/Toast';
import AppShell from './AppShell';
import SettingsPage from '../pages/SettingsPage';

/**
 * The redesign moved the shell from a Tools section to nouns-in-the-sidebar and
 * dropped the only link into settings on the way. `/settings` still routed, and
 * `/tools/settings` still redirected to it, so the page was live and
 * unreachable — which is the same as missing for anyone who does not type URLs.
 * Device pairing lives there, so this is the door to every other machine.
 */

function shell() {
  return renderToString(
    <StaticRouter location="/">
      <AppProvider>
        <ToastProvider>
          <AppShell />
        </ToastProvider>
      </AppProvider>
    </StaticRouter>,
  );
}

describe('the shell', () => {
  it('offers a way into settings', () => {
    expect(shell()).toContain('aria-label="Settings"');
  });
});

describe('the settings page', () => {
  it('renders inside the shell scroll container, so a long page can reach its end', () => {
    const html = renderToString(
      <StaticRouter location="/settings">
        <AppProvider>
          <ToastProvider>
            <SettingsPage />
          </ToastProvider>
        </AppProvider>
      </StaticRouter>,
    );

    // `.canvas` is `overflow: hidden`; `.surface` is the element that scrolls.
    expect(html).toMatch(/class="[^"]*\bsurface\b[^"]*"/);
  });
});
