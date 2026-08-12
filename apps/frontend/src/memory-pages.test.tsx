import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import ToolsPage from './pages/ToolsPage';
import MemoryPage from './pages/MemoryPage';
import GraphAuditPanel from './components/GraphAuditPanel';

describe('memory and graph audit surfaces', () => {
  it('exposes audit and memory as tools tabs', () => {
    const html = renderToString(
      <StaticRouter location="/tools/graph">
        <ToolsPage />
      </StaticRouter>,
    );

    expect(html).toContain('Audit');
    expect(html).toContain('Memory');
  });

  it('describes the memory tab as agent-facing governance', () => {
    const html = renderToString(
      <StaticRouter location="/tools/memory">
        <ToolsPage />
      </StaticRouter>,
    );

    expect(html).toContain('Memory Assets');
    expect(html).toContain('which assets each agent inherits');
  });

  it('describes the audit tab in provenance terms', () => {
    const html = renderToString(
      <StaticRouter location="/tools/audit">
        <ToolsPage />
      </StaticRouter>,
    );

    expect(html).toContain('Graph Audit');
    expect(html).toContain('surprising links');
  });

  it('renders the memory page with a loadout section', () => {
    const html = renderToString(
      <StaticRouter location="/tools/memory">
        <MemoryPage />
      </StaticRouter>,
    );

    expect(html).toContain('Memory assets');
    expect(html).toContain('Agent loadout');
    expect(html).toContain('Catalog existing memory');
  });

  it('renders the graph audit panel with its discovery sections', () => {
    const html = renderToString(
      <StaticRouter location="/tools/audit">
        <GraphAuditPanel />
      </StaticRouter>,
    );

    expect(html).toContain('Graph audit');
    expect(html).toContain('Shortest path');
  });
});
