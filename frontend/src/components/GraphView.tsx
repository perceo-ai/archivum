import { useEffect, useRef, useState } from 'react';
import type { Network, Options } from 'vis-network';
import { DataSet } from 'vis-data';
import { getGraph } from '../api';
import type { GraphNode, GraphEdge } from '../types';

interface GraphViewProps {
  onNavigate: (slug: string) => void;
}

const NODE_COLORS: Record<string, string> = {
  page: '#4B91F1',
  person: '#f9a825',
  concept: '#ab47bc',
  org: '#43a047',
  entity: '#78909c',
};

export default function GraphView({ onNavigate }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const nodesRef = useRef<DataSet<GraphNode & { color: string; font: { color: string } }> | null>(null);
  const edgesRef = useRef<DataSet<{ id: string; from: string; to: string; label: string }> | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState('');
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);

  async function loadGraph() {
    setLoading(true);
    setError(null);
    try {
      const { nodes, edges } = await getGraph();
      setNodeCount(nodes.length);
      setEdgeCount(edges.length);
      renderGraph(nodes, edges);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function renderGraph(nodes: GraphNode[], edges: GraphEdge[]) {
    if (!containerRef.current) return;

    const visNodes = new DataSet(
      nodes.map((n) => ({
        ...n,
        color: {
          background: NODE_COLORS[n.entity_type ?? n.type] ?? NODE_COLORS.entity,
          border: NODE_COLORS[n.entity_type ?? n.type] ?? NODE_COLORS.entity,
          highlight: {
            background: '#ffffff',
            border: '#4B91F1',
          },
          hover: {
            background: NODE_COLORS[n.entity_type ?? n.type] ?? NODE_COLORS.entity,
            border: '#ffffff',
          },
        },
        font: { color: '#cdd6f4', size: 11 },
        shape: n.type === 'page' ? 'dot' : 'diamond',
        size: n.type === 'page' ? 12 : 8,
      })),
    );

    const visEdges = new DataSet(
      edges.map((e, i) => ({
        id: `e${i}`,
        from: e.from,
        to: e.to,
        label: e.label,
        font: { color: '#6c7086', size: 9, align: 'middle' },
        color: { color: '#3a3a4a', highlight: '#4B91F1', hover: '#6c7086' },
        arrows: { to: { enabled: true, scaleFactor: 0.5 } },
        smooth: { enabled: true, type: 'dynamic', roundness: 0.2 },
      })),
    );

    nodesRef.current = visNodes as unknown as typeof nodesRef.current;
    edgesRef.current = visEdges as unknown as typeof edgesRef.current;

    const options: Options = {
      layout: {
        improvedLayout: true,
      },
      physics: {
        enabled: true,
        stabilization: { iterations: 100 },
        barnesHut: {
          gravitationalConstant: -2000,
          centralGravity: 0.3,
          springLength: 120,
          springConstant: 0.04,
          damping: 0.09,
        },
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        hideEdgesOnDrag: true,
        navigationButtons: false,
        keyboard: { enabled: true },
      },
      nodes: {
        borderWidth: 1,
        shadow: false,
      },
      edges: {
        width: 1,
        shadow: false,
        selectionWidth: 2,
      },
    };

    // Destroy existing network
    if (networkRef.current) {
      networkRef.current.destroy();
    }

    // Dynamic import to avoid SSR issues
    import('vis-network').then(({ Network }) => {
      if (!containerRef.current) return;
      const network = new Network(
        containerRef.current,
        { nodes: visNodes, edges: visEdges },
        options,
      );

      network.on('click', (params) => {
        if (params.nodes.length > 0) {
          const nodeId = String(params.nodes[0]);
          const node = visNodes.get(nodeId) as (GraphNode & { type: string }) | null;
          if (node && node.type === 'page') {
            onNavigate(nodeId);
          }
        }
      });

      network.on('stabilizationIterationsDone', () => {
        network.setOptions({ physics: { enabled: false } });
      });

      networkRef.current = network;
    });
  }

  useEffect(() => {
    loadGraph();
    return () => {
      networkRef.current?.destroy();
      networkRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSearch(text: string) {
    setSearchText(text);
    if (!networkRef.current || !nodesRef.current) return;

    if (!text.trim()) {
      // Reset all nodes
      const allIds = nodesRef.current.getIds();
      networkRef.current.selectNodes([]);
      void allIds;
      return;
    }

    const lower = text.toLowerCase();
    const matched = nodesRef.current
      .get()
      .filter((n: { label?: string }) => n.label?.toLowerCase().includes(lower))
      .map((n: { id?: string | number }) => n.id as string);

    if (matched.length > 0) {
      networkRef.current.selectNodes(matched);
      networkRef.current.focus(matched[0], { scale: 1.2, animation: true });
    }
  }

  function zoomIn() {
    if (!networkRef.current) return;
    const scale = networkRef.current.getScale();
    networkRef.current.moveTo({ scale: scale * 1.3, animation: true });
  }

  function zoomOut() {
    if (!networkRef.current) return;
    const scale = networkRef.current.getScale();
    networkRef.current.moveTo({ scale: scale * 0.77, animation: true });
  }

  function fitAll() {
    networkRef.current?.fit({ animation: true });
  }

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: '#1e1e2e' }}>
      {/* Toolbar */}
      <div
        className="flex items-center gap-2 px-4 py-2 border-b shrink-0"
        style={{ borderColor: '#3a3a4a', backgroundColor: '#252535' }}
      >
        <input
          type="text"
          placeholder="Find node..."
          value={searchText}
          onChange={(e) => handleSearch(e.target.value)}
          className="bg-transparent border rounded px-2 py-1 text-xs text-text-secondary placeholder-text-muted focus:outline-none focus:border-accent/50 w-48"
          style={{ borderColor: '#3a3a4a' }}
        />
        <div className="flex gap-1">
          <GraphButton onClick={zoomIn} title="Zoom in">+</GraphButton>
          <GraphButton onClick={zoomOut} title="Zoom out">−</GraphButton>
          <GraphButton onClick={fitAll} title="Fit all">⊡</GraphButton>
          <GraphButton onClick={loadGraph} title="Refresh">↻</GraphButton>
        </div>
        <div className="flex-1" />
        <span className="text-xs text-text-muted">
          {nodeCount} nodes · {edgeCount} edges
        </span>
        {/* Legend */}
        <div className="flex items-center gap-3">
          {Object.entries(NODE_COLORS).map(([type, color]) => (
            <div key={type} className="flex items-center gap-1">
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span className="text-xs text-text-muted capitalize">{type}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Graph container */}
      <div className="flex-1 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="space-y-2 w-48">
              <div className="skeleton h-4 w-full" />
              <div className="skeleton h-4 w-3/4" />
              <div className="skeleton h-4 w-5/6" />
            </div>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <p className="text-red-400 text-sm mb-3">{error}</p>
              <button
                onClick={loadGraph}
                className="text-xs px-3 py-1.5 rounded border border-accent/50 text-accent hover:bg-accent/10 transition-colors"
              >
                Retry
              </button>
            </div>
          </div>
        )}
        <div ref={containerRef} className="w-full h-full" />
      </div>
    </div>
  );
}

function GraphButton({
  onClick,
  title,
  children,
}: {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="w-7 h-7 flex items-center justify-center rounded border text-text-secondary hover:text-text-primary hover:border-accent/50 transition-colors text-sm"
      style={{ borderColor: '#3a3a4a' }}
    >
      {children}
    </button>
  );
}
