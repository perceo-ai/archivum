import { useEffect, useState } from 'react';
import { AlertTriangle, Check, GitMerge, RefreshCw, Shield, Split, X } from 'lucide-react';
import {
  expireSuggestions,
  listSuggestions,
  reviewSuggestion,
  type MemorySuggestion,
  type SuggestionReviewAction,
} from '../api';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';

const REVIEW_ACTIONS: Array<{
  action: SuggestionReviewAction;
  label: string;
  icon: typeof Check;
  variant?: 'outline' | 'ghost';
}> = [
  { action: 'accept', label: 'Accept', icon: Check, variant: 'outline' },
  { action: 'merge', label: 'Merge', icon: GitMerge, variant: 'outline' },
  { action: 'replace', label: 'Replace', icon: Split, variant: 'outline' },
  { action: 'keep_both', label: 'Keep both', icon: Shield, variant: 'outline' },
  { action: 'retire', label: 'Retire stale', icon: AlertTriangle, variant: 'outline' },
  { action: 'reject', label: 'Reject', icon: X, variant: 'ghost' },
];

export default function ReviewPage() {
  const [suggestions, setSuggestions] = useState<MemorySuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    setLoading(true);
    try {
      setSuggestions(await listSuggestions());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load suggestions');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function applyAction(suggestion: MemorySuggestion, action: SuggestionReviewAction) {
    setError(null);
    try {
      const updated = await reviewSuggestion(suggestion.id, action);
      setSuggestions((current) => current.filter((item) => item.id !== updated.id));
      setMessage(`Marked ${suggestion.suggestion_type} as ${updated.status}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update suggestion');
    }
  }

  async function expireDue() {
    setError(null);
    try {
      const expired = await expireSuggestions(new Date().toISOString());
      const expiredIds = new Set(expired.map((suggestion) => suggestion.id));
      setSuggestions((current) => current.filter((item) => !expiredIds.has(item.id)));
      setMessage(`${expired.length} stale suggestion${expired.length === 1 ? '' : 's'} expired.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to expire suggestions');
    }
  }

  return (
    <div className="page-frame bg-transparent">
      <div className="page-header">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          person:self
        </p>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0 flex-1">
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">Review</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Promote, merge, replace, scope, or retire proposed durable memory.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={expireDue}>
              <AlertTriangle className="h-4 w-4" />
              Expire stale
            </Button>
            <Button type="button" variant="secondary" onClick={refresh}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <div className="workspace-pane min-h-0 flex-1 overflow-y-auto">
        <div className="subtle-divider flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Review updates</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Why it matters · Scope · Durability · Agent visibility · Conflicts · Redundancy
            </p>
          </div>
          <Badge>{suggestions.length} pending</Badge>
        </div>
        <div className="space-y-4 p-5">
          {message && <p className="text-sm text-emerald-300">{message}</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}
          {suggestions.map((suggestion) => (
            <article key={suggestion.id} className="soft-border rounded-[8px] border bg-white/[0.03] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold text-foreground">{suggestion.suggestion_type}</h3>
                    <Badge>{suggestion.status}</Badge>
                    <Badge>{suggestion.retention_tier}</Badge>
                  </div>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                    {suggestion.proposed_markdown || suggestion.target_id}
                  </p>
                </div>
                <Badge>{suggestion.citations.length} cited</Badge>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <ReviewMeta label="Why it matters" value={suggestion.rationale || 'No rationale recorded.'} />
                <ReviewMeta label="Scope" value={suggestion.proposed_scopes.join(', ') || 'Unscoped'} />
                <ReviewMeta label="Durability" value={suggestion.estimated_durability || 'Unscored'} />
                <ReviewMeta label="Agent visibility" value={suggestion.agent_visibility} />
                <ReviewMeta label="Conflicts" value={suggestion.conflicts.join(', ') || 'None'} />
                <ReviewMeta label="Redundancy" value={suggestion.duplicates.join(', ') || 'None'} />
                <ReviewMeta label="Expires" value={suggestion.expires_at || 'No expiry'} />
                <ReviewMeta label="Scores" value={formatScores(suggestion.scores)} />
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {REVIEW_ACTIONS.map((item) => (
                  <Button
                    key={item.action}
                    size="sm"
                    variant={item.variant ?? 'outline'}
                    onClick={() => applyAction(suggestion, item.action)}
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </Button>
                ))}
              </div>
            </article>
          ))}
          {!loading && suggestions.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No pending review cards. New captures and distillation can propose durable updates here.
            </p>
          )}
          {loading && <p className="text-sm text-muted-foreground">Loading review cards...</p>}
        </div>
      </div>
    </div>
  );
}

function ReviewMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="soft-border rounded-[8px] border bg-black/10 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">{label}</p>
      <p className="mt-1 line-clamp-3 text-xs leading-5 text-muted-foreground">{value}</p>
    </div>
  );
}

function formatScores(scores: Record<string, number>) {
  const entries = Object.entries(scores);
  if (entries.length === 0) return 'No scores';
  return entries
    .map(([key, value]) => `${key.replace(/_/g, ' ')} ${Math.round(value * 100)}%`)
    .join(', ');
}
