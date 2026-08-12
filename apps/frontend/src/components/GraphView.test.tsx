import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import GraphView from './GraphView';

describe('GraphView', () => {
  it('keeps the owner visible as the default graph center', () => {
    const html = renderToString(<GraphView onNavigate={vi.fn()} />);

    expect(html).toContain('Me');
    expect(html).toContain('Center');
  });
});
