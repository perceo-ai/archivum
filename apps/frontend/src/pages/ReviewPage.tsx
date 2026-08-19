import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, GitMerge, Pencil, RefreshCw, Shield, Split, X } from 'lucide-react';
import {
  expireSuggestions,
  listMemoryAssets,
  listMemoryScopes,
  listSuggestions,
  reviewSuggestion,
  type MemoryAsset,
  type MemoryScope,
  type MemorySuggestion,
  type SuggestionReviewAction,
} from '../api';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Textarea } from '../components/ui/Textarea';

const VISIBILITIES = ['private', 'shared', 'public'] as const;

type ReviewOptions = {
  asset_id?: string;
  scope?: string;
  visibility?: string;
  edited_markdown?: string;
};

export default function ReviewPage() {
  const [suggestions, setSuggestions] = useState<MemorySuggestion[]>([]);
  const [assets, setAssets] = useState<MemoryAsset[]>([]);
  const [scopes, setScopes] = useState<MemoryScope[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    setLoading(true);
    try {
      const [nextSuggestions, nextAssets, nextScopes] = await Promise.all([
        listSuggestions(),
        listMemoryAssets(),
        listMemoryScopes(),
      ]);
      setSuggestions(nextSuggestions);
      setAssets(nextAssets);
      setScopes(nextScopes);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load suggestions');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function applyAction(
    suggestion: MemorySuggestion,
    action: SuggestionReviewAction,
    options: ReviewOptions,
  ) {
    setError(null);
    try {
      const updated = await reviewSuggestion(suggestion.id, action, options);
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
          Owner review
        </p>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0 flex-1">
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">Review</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Approve, edit, merge, or retire suggested memory before agents can use it.
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
            <SuggestionCard
              key={suggestion.id}
              suggestion={suggestion}
              assets={assets}
              scopes={scopes}
              onAction={applyAction}
            />
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

function SuggestionCard({
  suggestion,
  assets,
  scopes,
  onAction,
}: {
  suggestion: MemorySuggestion;
  assets: MemoryAsset[];
  scopes: MemoryScope[];
  onAction: (
    suggestion: MemorySuggestion,
    action: SuggestionReviewAction,
    options: ReviewOptions,
  ) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [editedMarkdown, setEditedMarkdown] = useState(suggestion.proposed_markdown);
  const [scope, setScope] = useState('');
  const [visibility, setVisibility] = useState('');
  const [targetId, setTargetId] = useState('');

  const scopeOptions = useMemo(() => {
    const known = new Set<string>();
    for (const item of suggestion.proposed_scopes) known.add(item);
    for (const item of scopes) known.add(item.id);
    known.add('person:self');
    return [...known].sort();
  }, [suggestion.proposed_scopes, scopes]);

  // Merge/replace/retire need something to act on: an explicit target here,
  // or a card that already names conflicting/duplicate memory.
  const implicitTargets = useMemo(
    () =>
      [suggestion.target_id, ...suggestion.conflicts, ...suggestion.duplicates].filter(
        (id) => id.startsWith('memory:'),
      ),
    [suggestion],
  );
  const hasTarget = targetId !== '' || implicitTargets.length > 0;

  const governance: ReviewOptions = {
    ...(scope ? { scope } : {}),
    ...(visibility ? { visibility } : {}),
  };
  const targeted: ReviewOptions = {
    ...governance,
    ...(targetId ? { asset_id: targetId } : {}),
  };

  return (
    <article className="soft-border rounded-[8px] border bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">{suggestion.suggestion_type}</h3>
            <Badge>{suggestion.status}</Badge>
            <Badge>{suggestion.retention_tier}</Badge>
          </div>
          {!editing && (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              {suggestion.proposed_markdown || suggestion.target_id}
            </p>
          )}
        </div>
        <Badge>{suggestion.citations.length} cited</Badge>
      </div>

      {editing && (
        <div className="mt-3 space-y-2">
          <Textarea
            value={editedMarkdown}
            onChange={(event) => setEditedMarkdown(event.target.value)}
            className="min-h-[120px]"
            aria-label="Edit proposed memory"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={() =>
                onAction(suggestion, 'edit', { ...governance, edited_markdown: editedMarkdown })
              }
            >
              <Check className="h-4 w-4" />
              Save &amp; accept
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

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

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Accept into scope
          <select
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            className="soft-border rounded-[6px] border bg-black/20 px-2 py-1.5 text-sm text-foreground"
            aria-label="Accept into scope"
          >
            <option value="">Card default</option>
            {scopeOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Agent visibility
          <select
            value={visibility}
            onChange={(event) => setVisibility(event.target.value)}
            className="soft-border rounded-[6px] border bg-black/20 px-2 py-1.5 text-sm text-foreground"
            aria-label="Agent visibility"
          >
            <option value="">Card default</option>
            {VISIBILITIES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Merge/replace/retire target
          <select
            value={targetId}
            onChange={(event) => setTargetId(event.target.value)}
            className="soft-border rounded-[6px] border bg-black/20 px-2 py-1.5 text-sm text-foreground"
            aria-label="Merge, replace, or retire target"
          >
            <option value="">
              {implicitTargets.length > 0
                ? `Card targets (${implicitTargets.length})`
                : 'Choose existing memory'}
            </option>
            {assets.map((asset) => (
              <option key={asset.id} value={asset.id}>
                {asset.name} · {asset.status}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="mt-3 text-xs leading-5 text-muted-foreground">
        Accept creates reviewed memory. Merge or Replace updates the selected target.
        Keep both preserves this card as separate memory. Retire stale archives the selected target.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          title="Create reviewed memory from this card"
          onClick={() => onAction(suggestion, 'accept', governance)}
        >
          <Check className="h-4 w-4" />
          Accept
        </Button>
        <Button size="sm" variant="outline" onClick={() => setEditing((current) => !current)}>
          <Pencil className="h-4 w-4" />
          Edit
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!hasTarget}
          title={hasTarget ? 'Blend this card into the selected existing memory' : 'Choose a target memory first'}
          onClick={() => onAction(suggestion, 'merge', targeted)}
        >
          <GitMerge className="h-4 w-4" />
          Merge
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!hasTarget}
          title={hasTarget ? 'Replace the selected existing memory with this card' : 'Choose a target memory first'}
          onClick={() => onAction(suggestion, 'replace', targeted)}
        >
          <Split className="h-4 w-4" />
          Replace
        </Button>
        <Button
          size="sm"
          variant="outline"
          title="Keep this as separate reviewed memory"
          onClick={() => onAction(suggestion, 'keep_both', governance)}
        >
          <Shield className="h-4 w-4" />
          Keep both
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!hasTarget}
          title={hasTarget ? 'Archive the selected target as stale' : 'Choose a target memory first'}
          onClick={() => onAction(suggestion, 'retire', targetId ? { asset_id: targetId } : {})}
        >
          <AlertTriangle className="h-4 w-4" />
          Retire stale
        </Button>
        <Button
          size="sm"
          variant="ghost"
          title="Dismiss this suggestion without saving it"
          onClick={() => onAction(suggestion, 'reject', {})}
        >
          <X className="h-4 w-4" />
          Reject
        </Button>
      </div>
    </article>
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
