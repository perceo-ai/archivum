import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';

const getContextPackage = vi.hoisted(() => vi.fn());
const effects = vi.hoisted(() => [] as Array<() => void | (() => void)>);

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>();
  return { ...actual, useEffect: (effect: () => void | (() => void)) => { effects.push(effect); } };
});

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return { ...actual, getContextPackage };
});

import GraphView from './GraphView';

describe('GraphView', () => {
  beforeEach(() => {
    effects.length = 0;
    getContextPackage.mockReset();
    getContextPackage.mockResolvedValue({
      nodes: [],
      edges: [],
      citations: [],
      query: '',
      seeds: ['person:self'],
      insufficient_evidence: true,
      reason: null,
    });
  });

  it('keeps the owner visible as the default graph center', () => {
    const html = renderToString(<GraphView onNavigate={vi.fn()} />);

    expect(html).toContain('Me');
    expect(html).toContain('Center');
  });

  it('loads scoped context from the owner root on mount', async () => {
    renderToString(<GraphView onNavigate={vi.fn()} />);
    effects[0]?.();
    await Promise.resolve();

    expect(getContextPackage).toHaveBeenCalledWith({
      seed_ids: ['person:self'],
      depth: 2,
      max_nodes: 24,
    });
  });
});
