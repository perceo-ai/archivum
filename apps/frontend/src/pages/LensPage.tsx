import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { listMemoryScopes, type MemoryScope } from '../api';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';

const LENS_COPY: Record<string, { title: string; description: string; scopeType?: MemoryScope['scope_type'] }> = {
  topics: {
    title: 'Topics',
    description: 'Topic-scoped memory budgets, review status, and context lenses.',
    scopeType: 'topic',
  },
  people: {
    title: 'People',
    description: 'People and relationship memory connected back to person:self.',
    scopeType: 'person',
  },
  repos: {
    title: 'Repos',
    description: 'Repository context, code insights, and agent-ready technical memory.',
    scopeType: 'repo',
  },
  sources: {
    title: 'Sources',
    description: 'Original files, URLs, sessions, transcripts, and imported evidence.',
  },
};

export default function LensPage({ lens }: { lens: keyof typeof LENS_COPY }) {
  const config = LENS_COPY[lens];
  const [scopes, setScopes] = useState<MemoryScope[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      setScopes(await listMemoryScopes(config.scopeType));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load lens');
    }
  }

  useEffect(() => {
    refresh();
  }, [lens]);

  return (
    <div className="page-frame bg-transparent">
      <div className="page-header">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          person:self lens
        </p>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0 flex-1">
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">{config.title}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{config.description}</p>
          </div>
          <Button type="button" variant="secondary" onClick={refresh}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      <div className="workspace-pane min-h-0 flex-1 overflow-y-auto">
        <div className="subtle-divider flex items-center justify-between border-b px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">{config.title} lens</h2>
          <Badge>{scopes.length} scopes</Badge>
        </div>
        <div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-3">
          {scopes.map((scope) => (
            <article key={scope.id} className="soft-border rounded-[8px] border bg-white/[0.03] p-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="truncate text-sm font-semibold text-foreground">{scope.name}</h3>
                <Badge>{scope.scope_type}</Badge>
              </div>
              <p className="mt-2 truncate text-xs text-muted-foreground">{scope.id}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge>{scope.budget_tokens} tokens</Badge>
                <Badge>{scope.budget_items} items</Badge>
              </div>
            </article>
          ))}
          {scopes.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No scoped records yet. Captures, review cards, and repo ingestion can populate this lens.
            </p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
      </div>
    </div>
  );
}
