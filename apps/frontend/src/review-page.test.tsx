import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import fs from 'node:fs';
import path from 'node:path';
import { AppProvider } from './store';
import ReviewPage from './pages/ReviewPage';

describe('review workflow surface', () => {
  it('renders the review queue with expiry controls', () => {
    const html = renderToString(
      <StaticRouter location="/review">
        <AppProvider>
          <ReviewPage />
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('Review updates');
    expect(html).toContain('Expire stale');
  });

  it('exposes edit, scope, visibility, and target controls on cards', () => {
    // Static contract: the strategy's card actions must all be wired.
    const text = fs.readFileSync(path.resolve('src/pages/ReviewPage.tsx'), 'utf8');

    for (const action of [
      "'accept'",
      "'edit'",
      "'merge'",
      "'replace'",
      "'keep_both'",
      "'retire'",
      "'reject'",
    ]) {
      expect(text).toContain(action);
    }
    expect(text).toContain('edited_markdown');
    expect(text).toContain('Accept into scope');
    expect(text).toContain('Agent visibility');
    expect(text).toContain('Merge/replace/retire target');
    expect(text).toContain('asset_id');
  });
});
