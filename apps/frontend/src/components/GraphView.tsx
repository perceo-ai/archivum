import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Maximize, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import type { Color, Network, Options } from 'vis-network';
import { DataSet } from 'vis-data';
import { getContextPackage } from '../api';
import type { Citation, ContextNode } from '../api';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { ProvenanceDrawer } from './ProvenanceDrawer';
import { SelfNodeHeader } from './SelfNodeHeader';

interface GraphViewProps {
  onNavigate: (slug: string) => void;
}

type ScopedNode = ContextNode & { color: Color; font: { color: string }; shape: string; size: number; fixed?: { x: boolean; y: boolean }; x?: number; y?: number };

const NODE_COLORS: Record<string, string> = {
  page: '#4B91F1',
  person: '#f9a825',
  concept: '#ab47bc',
  org: '#43a047',
  entity: '#78909c',
};

const SELF_ID = 'person:self';
const INITIAL_GRAPH_SCALE = 1.15;

function pageSlug(sourceId: string): string | null {
  const parts = sourceId.split(':');
  if (parts[0] !== 'page') return null;
  return parts.length > 2 ? parts.slice(2).join(':') : parts[1] || null;
}

export default function GraphView({ onNavigate }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const nodesRef = useRef<DataSet<ScopedNode> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState('');
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [activeSeed, setActiveSeed] = useState(SELF_ID);
  const [activeScope, setActiveScope] = useState('wiki:default');
  const [selectedNode, setSelectedNode] = useState<ContextNode | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  async function loadGraph(seedId = activeSeed) {
    setLoading(true);
    setError(null);
    try {
      const context = await getContextPackage({ seed_ids: [seedId], depth: 2, max_nodes: 24 });
      setActiveSeed(seedId);
      setActiveScope(context.nodes.find((node) => node.id === SELF_ID)?.scope ?? context.nodes[0]?.scope ?? 'wiki:default');
      setNodeCount(context.nodes.length);
      setEdgeCount(context.edges.length);
      renderGraph(context.nodes, context.edges.map((edge) => ({ from: edge.from_id, to: edge.to_id, label: edge.relation })));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function renderGraph(nodes: ContextNode[], edges: Array<{ from: string; to: string; label: string }>) {
    if (!containerRef.current) return;
    const visNodes = new DataSet<ScopedNode>(nodes.map((node) => {
      const isSelf = node.id === SELF_ID;
      const color = NODE_COLORS[node.node_type] ?? NODE_COLORS.entity;
      return {
        ...node,
        color: { background: isSelf ? '#f9a825' : color, border: isSelf ? '#fde68a' : color, highlight: { background: '#ffffff', border: '#4B91F1' }, hover: { background: color, border: '#ffffff' } },
        font: { color: '#cdd6f4' },
        shape: isSelf ? 'star' : node.node_type === 'page' ? 'dot' : 'diamond',
        size: isSelf ? 20 : node.node_type === 'page' ? 12 : 8,
        ...(isSelf ? { fixed: { x: true, y: true }, x: 0, y: 0 } : {}),
      };
    }));
    const visEdges = new DataSet(edges.map((edge, index) => ({
      id: `e${index}`, from: edge.from, to: edge.to, label: edge.label,
      font: { color: '#6c7086', size: 9, align: 'middle' },
      color: { color: '#3a3a4a', highlight: '#4B91F1', hover: '#6c7086' },
      arrows: { to: { enabled: true, scaleFactor: 0.5 } }, smooth: { enabled: true, type: 'dynamic', roundness: 0.2 },
    })));
    nodesRef.current = visNodes;
    networkRef.current?.destroy();

    const options: Options = {
      layout: { improvedLayout: true },
      physics: { enabled: true, stabilization: { iterations: 100 }, barnesHut: { gravitationalConstant: -2000, centralGravity: 0.3, springLength: 120, springConstant: 0.04, damping: 0.09 } },
      interaction: { hover: true, tooltipDelay: 200, hideEdgesOnDrag: true, navigationButtons: false, keyboard: { enabled: true } },
      nodes: { borderWidth: 1, shadow: false }, edges: { width: 1, shadow: false, selectionWidth: 2 },
    };

    void import('vis-network').then(({ Network }) => {
      if (!containerRef.current) return;
      const network = new Network(containerRef.current, { nodes: visNodes, edges: visEdges }, options);
      network.on('click', (params) => {
        const nodeId = params.nodes[0] ? String(params.nodes[0]) : null;
        if (!nodeId) return;
        const node = visNodes.get(nodeId);
        if (!node) return;
        setSelectedNode(node);
        setDrawerOpen(true);
      });
      network.on('doubleClick', (params) => {
        const nodeId = params.nodes[0] ? String(params.nodes[0]) : null;
        if (nodeId) void loadGraph(nodeId);
      });
      network.on('stabilizationIterationsDone', () => {
        network.setOptions({ physics: { enabled: false } });
        network.moveTo({ position: { x: 0, y: 0 }, scale: INITIAL_GRAPH_SCALE, animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
      });
      networkRef.current = network;
    });
  }

  useEffect(() => {
    void loadGraph(SELF_ID);
    return () => { networkRef.current?.destroy(); networkRef.current = null; };
    // Initial load must always start at the owner root.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSearch(text: string) {
    setSearchText(text);
    if (!networkRef.current || !nodesRef.current) return;
    if (!text.trim()) { networkRef.current.selectNodes([]); return; }
    const matched = nodesRef.current.get().filter((node) => node.label.toLowerCase().includes(text.toLowerCase())).map((node) => node.id);
    if (matched.length > 0) { networkRef.current.selectNodes(matched); networkRef.current.focus(matched[0], { scale: 1.2, animation: true }); }
  }

  function handleCitationClick(citation: Citation) {
    const slug = pageSlug(citation.source_id);
    if (slug) onNavigate(slug);
  }

  return (
    <div className="flex h-full w-full flex-col bg-transparent">
      <div className="subtle-divider flex shrink-0 items-center gap-3 border-b bg-white/[0.02] px-4 py-2 backdrop-blur">
        <SelfNodeHeader label="Me" activeScope={activeScope} />
        <div className="h-6 border-l border-white/[0.08]" />
        <Input type="text" placeholder="Find node..." value={searchText} onChange={(event) => handleSearch(event.target.value)} className="h-8 w-48 text-xs" />
        <div className="flex gap-1">
          <GraphButton onClick={() => networkRef.current?.moveTo({ scale: (networkRef.current?.getScale() ?? 1) * 1.3, animation: true })} title="Zoom in"><ZoomIn className="h-4 w-4" /></GraphButton>
          <GraphButton onClick={() => networkRef.current?.moveTo({ scale: (networkRef.current?.getScale() ?? 1) * 0.77, animation: true })} title="Zoom out"><ZoomOut className="h-4 w-4" /></GraphButton>
          <GraphButton onClick={() => networkRef.current?.fit({ animation: true })} title="Fit graph"><Maximize className="h-4 w-4" /></GraphButton>
          <GraphButton onClick={() => void loadGraph(activeSeed)} title="Refresh graph"><RotateCcw className="h-4 w-4" /></GraphButton>
        </div>
        <div className="flex-1" />
        <span className="text-xs text-muted-foreground">{nodeCount} nodes · {edgeCount} edges</span>
      </div>
      <div className="relative min-h-0 flex-1">
        {loading && <div className="absolute inset-0 z-10 flex items-center justify-center"><div className="w-48 space-y-2"><div className="skeleton h-4 w-full" /><div className="skeleton h-4 w-3/4" /><div className="skeleton h-4 w-5/6" /></div></div>}
        {error && <div className="absolute inset-0 z-10 flex items-center justify-center"><div className="text-center"><p className="mb-3 text-sm text-red-400">{error}</p><Button onClick={() => void loadGraph(activeSeed)} variant="secondary" size="sm">Retry</Button></div></div>}
        {!loading && !error && nodeCount === 0 && <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center text-sm text-muted-foreground">No scoped context is available for this center.</div>}
        <div ref={containerRef} className="h-full w-full" />
        <ProvenanceDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} citations={selectedNode?.citations ?? []} extractionMethod={selectedNode?.extraction_method} confidence={selectedNode?.confidence} onCitationClick={handleCitationClick} />
      </div>
    </div>
  );
}

function GraphButton({ onClick, title, children }: { onClick: () => void; title: string; children: ReactNode }) {
  return <Button onClick={onClick} title={title} variant="secondary" size="icon" className="h-8 w-8">{children}</Button>;
}
