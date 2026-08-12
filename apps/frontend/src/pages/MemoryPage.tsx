import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  bindMemoryAsset,
  catalogMemoryAssets,
  getAgentLoadout,
  listAgentBindings,
  listMemoryAgents,
  listMemoryAssets,
  setMemoryAssetStatus,
  unbindMemoryAsset,
  upsertMemoryAgent,
  type AgentProfile,
  type AssetBinding,
  type LoadoutPackage,
  type MemoryAsset,
} from '../api';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';

const LAYER_LABELS: Record<string, string> = {
  L0: 'L0 · raw evidence',
  L1: 'L1 · atoms',
  L2: 'L2 · scenario',
  L3: 'L3 · persona',
};

const NEXT_STATUS: Record<MemoryAsset['status'], MemoryAsset['status']> = {
  draft: 'active',
  active: 'archived',
  archived: 'active',
};

export default function MemoryPage() {
  const [assets, setAssets] = useState<MemoryAsset[]>([]);
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [bindings, setBindings] = useState<AssetBinding[]>([]);
  const [loadout, setLoadout] = useState<LoadoutPackage | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [agentKey, setAgentKey] = useState('');
  const [loadoutQuery, setLoadoutQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [cataloging, setCataloging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshAssets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextAssets, nextAgents] = await Promise.all([
        listMemoryAssets(),
        listMemoryAgents(),
      ]);
      setAssets(nextAssets);
      setAgents(nextAgents);
      if (!selectedAgent && nextAgents.length > 0) {
        setSelectedAgent(nextAgents[0].agent_key);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load memory assets');
    } finally {
      setLoading(false);
    }
  }, [selectedAgent]);

  useEffect(() => {
    refreshAssets();
  }, [refreshAssets]);

  const refreshAgentView = useCallback(async () => {
    if (!selectedAgent) {
      setBindings([]);
      setLoadout(null);
      return;
    }
    try {
      const [nextBindings, nextLoadout] = await Promise.all([
        listAgentBindings(selectedAgent),
        getAgentLoadout(selectedAgent, loadoutQuery),
      ]);
      setBindings(nextBindings);
      setLoadout(nextLoadout);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load agent loadout');
    }
  }, [selectedAgent, loadoutQuery]);

  useEffect(() => {
    refreshAgentView();
  }, [refreshAgentView]);

  const boundIds = useMemo(
    () => new Set(bindings.map((binding) => binding.asset_id)),
    [bindings],
  );

  const byLayer = useMemo(() => {
    const grouped = new Map<string, MemoryAsset[]>();
    for (const asset of assets) {
      const list = grouped.get(asset.layer) ?? [];
      list.push(asset);
      grouped.set(asset.layer, list);
    }
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [assets]);

  async function cycleStatus(asset: MemoryAsset) {
    try {
      await setMemoryAssetStatus(asset.id, NEXT_STATUS[asset.status]);
      await refreshAssets();
      await refreshAgentView();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update asset status');
    }
  }

  async function toggleBinding(asset: MemoryAsset) {
    if (!selectedAgent) return;
    try {
      if (boundIds.has(asset.id)) {
        await unbindMemoryAsset(selectedAgent, asset.id);
      } else {
        await bindMemoryAsset(selectedAgent, { asset_id: asset.id });
      }
      await refreshAgentView();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update binding');
    }
  }

  async function runCatalog() {
    setCataloging(true);
    setError(null);
    try {
      await catalogMemoryAssets();
      await refreshAssets();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to catalog memory');
    } finally {
      setCataloging(false);
    }
  }

  async function createAgent(event: React.FormEvent) {
    event.preventDefault();
    const key = agentKey.trim();
    if (!key) return;
    try {
      await upsertMemoryAgent({ agent_key: key, name: key });
      setAgentKey('');
      setSelectedAgent(key);
      await refreshAssets();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create agent');
    }
  }

  return (
    <div className="w-full flex-1 overflow-y-auto p-4">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Memory assets</h1>
        <div className="flex gap-2">
          <Button
            onClick={runCatalog}
            variant="outline"
            size="sm"
            disabled={cataloging}
            title="Register existing pages, sources, and code graphs as governed assets"
          >
            {cataloging ? 'Cataloguing…' : 'Catalog existing memory'}
          </Button>
          <Button onClick={refreshAssets} variant="outline" size="sm" disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </Button>
        </div>
      </div>

      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Agent loadout</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {agents.map((agent) => (
              <Button
                key={agent.agent_key}
                size="sm"
                variant={agent.agent_key === selectedAgent ? 'default' : 'outline'}
                onClick={() => setSelectedAgent(agent.agent_key)}
              >
                {agent.name}
              </Button>
            ))}
            {agents.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No agents yet. Create one to decide which memory it inherits.
              </p>
            )}
          </div>

          <form className="flex gap-2" onSubmit={createAgent}>
            <Input
              value={agentKey}
              onChange={(event) => setAgentKey(event.target.value)}
              placeholder="new agent key"
              aria-label="New agent key"
            />
            <Button type="submit" size="sm" variant="outline">
              Add agent
            </Button>
          </form>

          {selectedAgent && (
            <>
              <Input
                value={loadoutQuery}
                onChange={(event) => setLoadoutQuery(event.target.value)}
                placeholder="session query (matches on-demand bindings)"
                aria-label="Loadout query"
              />
              {loadout && loadout.entries.length > 0 ? (
                <ul className="space-y-2">
                  {loadout.entries.map((entry) => (
                    <li
                      key={entry.asset.id}
                      className="soft-border rounded-[8px] border bg-white/[0.03] px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm text-foreground">{entry.asset.name}</span>
                        <Badge>{entry.mode}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{entry.reason}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {loadout?.reason ?? 'This agent inherits nothing yet.'}
                </p>
              )}
              {loadout?.insufficient_evidence && loadout.entries.length > 0 && (
                <p className="text-xs text-destructive">{loadout.reason}</p>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {byLayer.map(([layer, layerAssets]) => (
        <Card key={layer} className="mb-4">
          <CardHeader>
            <CardTitle>{LAYER_LABELS[layer] ?? layer}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {layerAssets.map((asset) => (
              <div
                key={asset.id}
                className="soft-border flex flex-wrap items-center justify-between gap-2 rounded-[8px] border bg-white/[0.03] px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm text-foreground">{asset.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {asset.summary || asset.id}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge>{asset.asset_type}</Badge>
                  <Badge>{asset.status}</Badge>
                  <Badge>v{asset.version}</Badge>
                  <Badge>{asset.citations.length} cited</Badge>
                  <Button size="sm" variant="outline" onClick={() => cycleStatus(asset)}>
                    {NEXT_STATUS[asset.status] === 'active' ? 'Activate' : 'Archive'}
                  </Button>
                  {selectedAgent && (
                    <Button size="sm" variant="outline" onClick={() => toggleBinding(asset)}>
                      {boundIds.has(asset.id) ? 'Unbind' : 'Bind'}
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}

      {!loading && assets.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No memory assets yet. Capture a session, then distil it to build layered memory.
        </p>
      )}
    </div>
  );
}
