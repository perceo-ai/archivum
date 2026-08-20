import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getGraph,
  getGraphAudit,
  getMemoryStats,
  getOwner,
  listAgentBindings,
  listMemoryAgents,
  listRepos,
  type AgentProfile,
  type CodeRepo,
  type GraphCommunity,
  type GraphReport,
  type MemoryStats,
  type OwnerProfile,
} from '../api';
import type { GraphEdge, GraphNode } from '../types';
import { Icon } from '../shell/Icon';
import { cn } from '../lib/cn';

/**
 * The structures under the vault, drawn from the stores that hold them.
 *
 * Nothing here is synthesised for the picture: rings come from graph
 * communities, the funnel from memory stats, the agent bars from bindings. If a
 * number is unavailable the panel says so rather than inventing a plausible one.
 */

type Tab = 'graph' | 'flow' | 'agents';

const RING_RADIUS = 190;
const LEAF_RADIUS = 320;

function ringLayout(count: number, index: number) {
  const angle = -90 + index * (360 / Math.max(count, 1));
  const radians = (angle * Math.PI) / 180;
  return {
    angle,
    x: 500 + Math.cos(radians) * RING_RADIUS,
    y: 280 + Math.sin(radians) * RING_RADIUS * 0.72,
  };
}

function leafPosition(angle: number, offset: number) {
  const radians = ((angle + offset) * Math.PI) / 180;
  return {
    x: 500 + Math.cos(radians) * LEAF_RADIUS,
    y: 280 + Math.sin(radians) * LEAF_RADIUS * 0.72,
  };
}

/**
 * Group page nodes by their top-level folder.
 *
 * Used when the knowledge store has not found link communities yet, which is
 * the normal state of a young vault. Folders are the user's own grouping, so
 * this is still their structure — not a guess.
 */
function foldersAsCommunities(nodes: GraphNode[]): GraphCommunity[] {
  const groups = new Map<string, string[]>();
  for (const node of nodes) {
    if (node.type !== 'page') continue;
    const folder = node.id.includes('/') ? node.id.split('/')[0] : 'root';
    const members = groups.get(folder) ?? [];
    members.push(node.id);
    groups.set(folder, members);
  }
  return [...groups.entries()]
    .map(([label, member_ids]) => ({
      id: `folder:${label}`,
      label,
      size: member_ids.length,
      member_ids,
    }))
    .sort((a, b) => b.size - a.size);
}

/** Mirror of the backend slug used when writing `code/<repo>/<cluster>.md`. */
function clusterSlug(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'untitled';
}


function GraphPanel({
  owner,
  audit,
  nodes,
  isDemo,
  repo,
  onOpenCluster,
}: {
  owner: OwnerProfile | null;
  audit: GraphReport | null;
  nodes: GraphNode[];
  isDemo: boolean;
  /** The repository being looked at, or null for the vault itself. */
  repo: CodeRepo | null;
  onOpenCluster: (community: GraphCommunity) => void;
}) {
  const communities = audit?.communities ?? [];

  // Names come from the same report the clusters came from. They used to be
  // looked up in a second, unscoped call, so pointing this at a repository
  // rendered rows of `repo_atlas_geo_haversine` instead of function names.
  const labelById = useMemo(() => {
    const map = new Map<string, string>();
    for (const [id, label] of Object.entries(audit?.node_labels ?? {})) map.set(id, label);
    for (const node of nodes) if (!map.has(node.id)) map.set(node.id, node.label);
    return map;
  }, [audit, nodes]);

  const kindById = audit?.node_kinds ?? {};

  // A repository is not you, so drawing your initials in the middle of a call
  // graph would be nonsense. The centre is whatever the graph is *of*.
  const centreLabel = repo ? repo.name : owner?.name ?? 'You';
  const centreInitials = repo ? repo.name.slice(0, 2).toUpperCase() : owner?.initials ?? '··';
  const centreSubtitle = repo
    ? `${audit?.node_count ?? 0} records · ${audit?.edge_count ?? 0} links`
    : 'person · self';

  const fromLinks = communities.length > 0;
  const rings = (fromLinks ? communities : foldersAsCommunities(nodes)).slice(0, 8);

  if (rings.length === 0) {
    return (
      <div className="stream-empty">
        <h3>Nothing to draw yet</h3>
        <p>
          Capture a few entries and the shape of your vault — you at the centre, your subjects
          around you — will appear here.
        </p>
      </div>
    );
  }

  return (
    <>
      {isDemo && (
        <div className="demo-banner">
          <Icon name="alert" />
          <span>
            The graph store is unreachable, so this is example data — not your vault. Check that
            Kuzu is running.
          </span>
        </div>
      )}
      <div className="mapwrap" style={{ margin: '0 18px 18px', height: 460 }}>
        <div className="grid-dots" />
        <svg width="100%" height="100%" viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid meet">
          {rings.map((community, index) => {
            const { x, y, angle } = ringLayout(rings.length, index);
            const members = community.member_ids.slice(0, 3);
            return (
              <g key={community.id}>
                <line className="glink hot" x1={500} y1={280} x2={x} y2={y} />
                {members.map((memberId, memberIndex) => {
                  const spread = (memberIndex - (members.length - 1) / 2) * 17;
                  const leaf = leafPosition(angle, spread);
                  return (
                    <g className="gnode" key={memberId}>
                      <line className="glink" x1={x} y1={y} x2={leaf.x} y2={leaf.y} />
                      <circle
                        cx={leaf.x}
                        cy={leaf.y}
                        r={kindById[memberId] === 'type' ? 8 : 6.5}
                        fill="var(--a-500)"
                        opacity={kindById[memberId] === 'file' ? 0.35 : 0.6}
                      />
                      <text x={leaf.x} y={leaf.y + 17} textAnchor="middle">
                        {labelById.get(memberId) ?? memberId}
                      </text>
                    </g>
                  );
                })}
                <g
                  className="gnode"
                  role={repo ? 'button' : undefined}
                  style={repo ? { cursor: 'pointer' } : undefined}
                  onClick={() => repo && onOpenCluster(community)}
                >
                  <circle
                    cx={x}
                    cy={y}
                    r={11 + Math.sqrt(Math.max(community.size, 1)) * 1.5}
                    fill="var(--a-500)"
                    opacity={0.8}
                    stroke="var(--bg-panel)"
                    strokeWidth={2}
                  />
                  <text x={x} y={y + 30} textAnchor="middle" style={{ fontWeight: 600, fontSize: 11.5 }}>
                    {community.label}
                  </text>
                  <text x={x} y={y + 43} textAnchor="middle" style={{ fontSize: 10, opacity: 0.7 }}>
                    {community.size}
                  </text>
                </g>
              </g>
            );
          })}

          <g className="gnode">
            <circle cx={500} cy={280} r={62} fill="var(--a-500)" opacity={0.07} />
            <circle cx={500} cy={280} r={46} fill="var(--a-500)" opacity={0.13} />
            <circle cx={500} cy={280} r={30} fill="var(--a-500)" />
            <text x={500} y={285} textAnchor="middle" style={{ fontSize: 15, fontWeight: 600, fill: '#fff' }}>
              {centreInitials}
            </text>
            <text x={500} y={332} textAnchor="middle" style={{ fontSize: 12, fontWeight: 600, fill: 'var(--a-500)' }}>
              {centreLabel}
            </text>
            <text x={500} y={346} textAnchor="middle" style={{ fontSize: 10 }}>
              {centreSubtitle}
            </text>
          </g>
        </svg>
        <div className="legend">
          <div>
            <span className="dot" style={{ background: 'var(--a-500)' }} />
            {repo
              ? 'Clusters found in how the code calls itself — click one to read its page'
              : fromLinks
                ? 'Clusters found in the links between entries'
                : 'Grouped by the folders you made — no link clusters yet'}
          </div>
        </div>
      </div>
    </>
  );
}

function FlowPanel({ stats }: { stats: MemoryStats | null }) {
  if (!stats) return <div className="surface-loading">Counting…</div>;

  const steps = [
    {
      label: 'Proposed',
      value: stats.suggestions_total,
      note: 'everything an agent or an ingest ever put forward',
    },
    {
      label: 'You kept',
      value: stats.suggestions_kept,
      note: `${stats.suggestions_dropped} rejected · ${stats.suggestions_pending} still waiting on you`,
    },
    {
      label: 'Live memory',
      value: stats.assets_active,
      note: `${stats.assets_archived} switched off · ${stats.assets_draft} still drafts`,
    },
  ];

  const max = Math.max(...steps.map((step) => step.value), 1);

  if (stats.suggestions_total === 0 && stats.assets_total === 0) {
    return (
      <div className="stream-empty">
        <h3>Nothing has been distilled yet</h3>
        <p>
          When an agent proposes something, or a source is read, the pipeline from proposal to live
          memory shows up here.
        </p>
      </div>
    );
  }

  return (
    <div className="panel-body">
      <div style={{ display: 'grid', gap: 22, padding: '8px 0 4px' }}>
        {steps.map((step) => (
          <div key={step.label} style={{ display: 'grid', gridTemplateColumns: '150px minmax(0,1fr)', gap: 16, alignItems: 'center' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 'var(--t-13)', fontWeight: 600 }}>{step.label}</div>
              <div style={{ fontSize: 'var(--t-11)', color: 'var(--text-3)' }}>
                {step.value.toLocaleString()}
              </div>
            </div>
            <div>
              <div
                style={{
                  height: 34,
                  width: `${Math.max((step.value / max) * 100, 2)}%`,
                  background: 'var(--accent)',
                  borderRadius: 'var(--r-sm)',
                  opacity: 0.85,
                }}
              />
              <div style={{ fontSize: 'var(--t-11)', color: 'var(--text-3)', marginTop: 6 }}>
                {step.note}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="legend-row">
        {stats.assets_disputed > 0 && (
          <span className="lg">
            <span className="sw" style={{ background: 'var(--warn)' }} />
            {stats.assets_disputed} disputed
          </span>
        )}
        {Object.entries(stats.assets_by_layer).map(([layer, count]) => (
          <span className="lg" key={layer}>
            {layer} <span className="v">{count}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function AgentsPanel({ agents }: { agents: AgentProfile[] }) {
  const [counts, setCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      agents.map((agent) =>
        listAgentBindings(agent.agent_key)
          .then((bindings) => [agent.agent_key, bindings.length] as const)
          .catch(() => [agent.agent_key, 0] as const),
      ),
    ).then((pairs) => {
      if (!cancelled) setCounts(Object.fromEntries(pairs));
    });
    return () => {
      cancelled = true;
    };
  }, [agents]);

  if (agents.length === 0) {
    return (
      <div className="stream-empty">
        <h3>No agents connected</h3>
        <p>Point an MCP client at Archivum and it will show up here with what it can read.</p>
      </div>
    );
  }

  const max = Math.max(...Object.values(counts), 1);

  return (
    <div className="panel-body" id="agentList">
      {agents.map((agent) => (
        <div className="agent-card" key={agent.agent_key}>
          <div className="agent-id">
            <Icon name="bot" />
            <span>
              <span className="t">{agent.name || agent.agent_key}</span>
              <br />
              <span className="s">{agent.description || agent.agent_key}</span>
            </span>
          </div>
          <div>
            <div className="bar-track">
              <span
                style={{
                  background: 'var(--accent)',
                  width: `${((counts[agent.agent_key] ?? 0) / max) * 100}%`,
                }}
              />
              <span style={{ background: 'var(--bg-active)', flex: 1 }} />
            </div>
            <div className="agent-meta">
              <span className="chip chip-accent">
                {counts[agent.agent_key] ?? 0} memories bound
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function VisualizedSurface() {
  const [tab, setTab] = useState<Tab>('graph');
  const [owner, setOwner] = useState<OwnerProfile | null>(null);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [audit, setAudit] = useState<GraphReport | null>(null);
  const [graph, setGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[]; source?: string } | null>(
    null,
  );
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [repos, setRepos] = useState<CodeRepo[]>([]);
  // Undefined means the vault itself; a repo scope points the same analysis at
  // code. The clustering and surprise algorithms never cared which graph they
  // were given — only the routes did.
  const [scope, setScope] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    listRepos()
      .then((next) => setRepos(next.filter((repo) => repo.status === 'ready')))
      .catch(() => setRepos([]));
  }, []);

  useEffect(() => {
    Promise.all([
      getOwner(),
      getMemoryStats(),
      getGraphAudit(10, scope).catch(() => null),
      getGraph().catch(() => null),
      listMemoryAgents().catch(() => []),
    ])
      .then(([nextOwner, nextStats, nextAudit, nextGraph, nextAgents]) => {
        setOwner(nextOwner);
        setStats(nextStats);
        setAudit(nextAudit);
        setGraph(nextGraph);
        setAgents(nextAgents);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load'));
  }, [scope]);

  if (error) return <div className="surface-error">{error}</div>;

  const activeRepo = repos.find((entry) => entry.scope === scope) ?? null;

  return (
    <div className="surface on viz-root">
      <div className="col-wide">
        <div className="viz-head">
          <div className="viz-title">
            <h1>Visualized</h1>
            <p>What is actually under the vault — the graph, the memory pipeline, and who reads what.</p>
            {repos.length > 0 && (
              <div className="viz-scope" style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                <button
                  type="button"
                  className={cn('btn btn-sm', scope === undefined ? 'btn-primary' : 'btn-outline')}
                  onClick={() => setScope(undefined)}
                >
                  Your vault
                </button>
                {repos.map((repo) => (
                  <button
                    key={repo.scope}
                    type="button"
                    className={cn('btn btn-sm', scope === repo.scope ? 'btn-primary' : 'btn-outline')}
                    onClick={() => setScope(repo.scope)}
                  >
                    {repo.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="tiles">
            <div className="tile">
              <div className="lab">Entries</div>
              <div className="num">{owner?.pages ?? '—'}</div>
              <div className="sub">pages on disk</div>
            </div>
            <div className="tile">
              <div className="lab">Links</div>
              <div className="num">{graph ? graph.edges.length : '—'}</div>
              <div className="sub">
                {audit && audit.orphan_ids.length > 0
                  ? `${audit.orphan_ids.length} link to nothing`
                  : 'between your entries'}
              </div>
            </div>
            <div className="tile">
              <div className="lab">Live memory</div>
              <div className="num">{stats?.assets_active ?? '—'}</div>
              <div className="sub">
                {stats ? `${stats.assets_archived} switched off` : ''}
              </div>
            </div>
            <div className="tile">
              <div className="lab">Waiting on you</div>
              <div className="num" style={{ color: 'var(--warn)' }}>
                {stats?.suggestions_pending ?? '—'}
              </div>
              <div className="sub">
                <button
                  type="button"
                  className="btn btn-sm"
                  style={{ padding: 0, height: 'auto' }}
                  onClick={() => navigate('/entries?needs_review=1')}
                >
                  Review them
                </button>
              </div>
            </div>
          </div>

          <div className="viz-tabs">
            <button type="button" className={cn(tab === 'graph' && 'on')} onClick={() => setTab('graph')}>
              <Icon name="graph" />
              Graph
            </button>
            <button type="button" className={cn(tab === 'flow' && 'on')} onClick={() => setTab('flow')}>
              <Icon name="merge" />
              Memory flow
            </button>
            <button type="button" className={cn(tab === 'agents' && 'on')} onClick={() => setTab('agents')}>
              <Icon name="bot" />
              Agents
            </button>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>
                {tab === 'graph'
                  ? 'Knowledge graph'
                  : tab === 'flow'
                    ? 'How something becomes a memory'
                    : 'What your agents can read'}
              </h2>
              <p>
                {tab === 'graph'
                  ? 'You are the root. Clusters hang off you, entries hang off clusters.'
                  : tab === 'flow'
                    ? 'Every claim starts as a proposal. Most do not survive review — that is the pipeline working.'
                    : 'Each agent sees only what it is bound to. Turning a memory off removes it here immediately.'}
              </p>
            </div>
          </div>

          {tab === 'graph' && (
            <GraphPanel
              owner={owner}
              audit={audit}
              nodes={graph?.nodes ?? []}
              isDemo={scope === undefined && graph?.source === 'demo'}
              repo={activeRepo}
              onOpenCluster={(community) =>
                activeRepo &&
                navigate(`/wiki/code/${activeRepo.name}/${clusterSlug(community.label)}`)
              }
            />
          )}
          {tab === 'flow' && <FlowPanel stats={stats} />}
          {tab === 'agents' && <AgentsPanel agents={agents} />}
        </div>
      </div>
    </div>
  );
}
