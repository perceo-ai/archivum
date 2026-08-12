import { useCallback, useEffect, useState } from 'react';
import { getGraphAudit, getGraphPath, type GraphPathResult, type GraphReport } from '../api';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from './ui/Card';
import { Input } from './ui/Input';

export default function GraphAuditPanel() {
  const [report, setReport] = useState<GraphReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [path, setPath] = useState<GraphPathResult | null>(null);
  const [pathError, setPathError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await getGraphAudit());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to audit the graph');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function findPath(event: React.FormEvent) {
    event.preventDefault();
    setPathError(null);
    setPath(null);
    if (!source.trim() || !target.trim()) return;
    try {
      setPath(await getGraphPath(source.trim(), target.trim()));
    } catch (e) {
      setPathError(e instanceof Error ? e.message : 'Failed to find a path');
    }
  }

  return (
    <div className="w-full flex-1 overflow-y-auto p-4">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Graph audit</h1>
        <Button onClick={refresh} variant="outline" size="sm" disabled={loading}>
          {loading ? 'Auditing…' : 'Refresh'}
        </Button>
      </div>

      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}

      {report && (
        <>
          <Card className="mb-4">
            <CardHeader>
              <CardTitle>What the graph says</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {report.narrative.map((line) => (
                <p key={line} className="text-sm leading-6 text-muted-foreground">
                  {line}
                </p>
              ))}
              <div className="flex flex-wrap gap-2 pt-2">
                <Badge>{report.node_count} records</Badge>
                <Badge>{report.edge_count} relationships</Badge>
                <Badge>{report.communities.length} clusters</Badge>
                <Badge>{report.self_cited_ids.length} self-cited</Badge>
                <Badge>{report.orphan_ids.length} unreachable</Badge>
              </div>
            </CardContent>
          </Card>

          <Card className="mb-4">
            <CardHeader>
              <CardTitle>Clusters</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {report.communities.slice(0, 12).map((community) => (
                <div
                  key={community.id}
                  className="soft-border flex items-center justify-between gap-2 rounded-[8px] border bg-white/[0.03] px-3 py-2"
                >
                  <span className="truncate text-sm text-foreground">{community.label}</span>
                  <Badge>{community.size} records</Badge>
                </div>
              ))}
              {report.communities.length === 0 && (
                <p className="text-sm text-muted-foreground">No clusters yet.</p>
              )}
            </CardContent>
          </Card>

          <Card className="mb-4">
            <CardHeader>
              <CardTitle>Surprising connections</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {report.surprising_links.map((link) => (
                <div
                  key={`${link.src_id}-${link.dst_id}-${link.rel_type}`}
                  className="soft-border rounded-[8px] border bg-white/[0.03] px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm text-foreground">
                      {link.src_label} → {link.dst_label}
                    </span>
                    <Badge>{link.score.toFixed(2)}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{link.reason}</p>
                </div>
              ))}
              {report.surprising_links.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  Nothing surprising: every connection is predictable from the rest of the graph.
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Shortest path</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <form className="flex flex-wrap gap-2" onSubmit={findPath}>
            <Input
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="source record id"
              aria-label="Path source"
            />
            <Input
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              placeholder="target record id"
              aria-label="Path target"
            />
            <Button type="submit" size="sm" variant="outline">
              Find path
            </Button>
          </form>

          {pathError && <p className="text-sm text-destructive">{pathError}</p>}

          {path && !path.found && (
            <p className="text-sm text-muted-foreground">{path.reason}</p>
          )}

          {path?.found && (
            <ol className="space-y-1">
              {path.steps.map((step) => (
                <li key={`${step.from_id}-${step.to_id}`} className="text-sm text-muted-foreground">
                  {step.from_id} —{step.relation}→ {step.to_id}
                </li>
              ))}
              {path.steps.length === 0 && (
                <li className="text-sm text-muted-foreground">Source and target are the same record.</li>
              )}
            </ol>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
