import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Archive, CheckCircle2, CircleAlert, Network, RefreshCw, Search, Send, Sparkles } from 'lucide-react';
import {
  captureConversation,
  distillSource,
  getContextPackage,
  listMemoryAssets,
  listSuggestions,
  reviewSuggestion,
  type ContextPackage,
  type DistillReport,
  type MemoryAsset,
  type MemorySuggestion,
  type SuggestionReviewAction,
} from '../api';
import { useAppDispatch } from '../store';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Textarea } from '../components/ui/Textarea';

const HOME_SCOPE = 'person:self';

function librarianSummary(report: DistillReport): string {
  const parts = [
    `Scanned ${report.sentences_scanned} sentence${report.sentences_scanned === 1 ? '' : 's'}`,
    `proposed ${report.atoms_pending_review} durable update${report.atoms_pending_review === 1 ? '' : 's'} for review`,
  ];
  const refused = Math.max(report.sentences_scanned - report.atoms_total, 0);
  if (refused > 0) parts.push(`left ${refused} as raw capture only`);
  if (report.conflicts_flagged > 0) {
    parts.push(`flagged ${report.conflicts_flagged} potential conflict${report.conflicts_flagged === 1 ? '' : 's'}`);
  }
  return `${parts.join(', ')}.`;
}

export default function HomePage() {
  const dispatch = useAppDispatch();
  const [captureText, setCaptureText] = useState('');
  const [saving, setSaving] = useState(false);
  const [distillAfterCapture, setDistillAfterCapture] = useState(true);
  const [suggestions, setSuggestions] = useState<MemorySuggestion[]>([]);
  const [assets, setAssets] = useState<MemoryAsset[]>([]);
  const [context, setContext] = useState<ContextPackage | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshHome() {
    setError(null);
    try {
      const [nextSuggestions, nextAssets, nextContext] = await Promise.all([
        listSuggestions(),
        listMemoryAssets({ status: 'active' }),
        getContextPackage({ scope: HOME_SCOPE, seed_ids: [HOME_SCOPE], depth: 1, max_nodes: 12 }),
      ]);
      setSuggestions(nextSuggestions);
      setAssets(nextAssets);
      setContext(nextContext);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load home context');
    }
  }

  useEffect(() => {
    refreshHome();
  }, []);

  const activeAssets = useMemo(
    () => assets.filter((asset) => asset.status === 'active').slice(0, 6),
    [assets],
  );

  async function handleCapture(event: React.FormEvent) {
    event.preventDefault();
    const text = captureText.trim();
    if (!text) return;
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      const captured = await captureConversation({
        session_id: `home-${Date.now()}`,
        interface: 'archivum_home',
        scope: HOME_SCOPE,
        turns: [{ role: 'user', text }],
      });
      let report: DistillReport | null = null;
      if (distillAfterCapture) {
        report = await distillSource({
          source_id: captured.source_id,
          scenario_key: 'home',
          write_pages: false,
        });
      }
      setCaptureText('');
      setStatus(
        distillAfterCapture && report
          ? librarianSummary(report)
          : `Captured raw source ${captured.source_id}.`,
      );
      await refreshHome();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to capture memory');
    } finally {
      setSaving(false);
    }
  }

  function openSearch() {
    dispatch({ type: 'SET_QUICK_SEARCH_OPEN', open: true });
  }

  async function handleReviewAction(
    suggestion: MemorySuggestion,
    action: SuggestionReviewAction,
  ) {
    setError(null);
    try {
      const updated = await reviewSuggestion(suggestion.id, action);
      setSuggestions((current) => current.filter((item) => item.id !== updated.id));
      setStatus(`Marked ${suggestion.suggestion_type} as ${updated.status}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update suggestion');
    }
  }

  return (
    <div className="page-frame bg-transparent">
      <div className="page-header">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0 flex-1">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              person:self
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">Home</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Capture broadly, review durable memory narrowly, and keep agent context visible.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={openSearch}>
              <Search className="h-4 w-4" />
              Quick ask
            </Button>
            <Button type="button" variant="outline" onClick={refreshHome}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <section className="workspace-pane flex min-h-[360px] flex-col overflow-hidden">
          <div className="subtle-divider border-b px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">What should Archivum remember?</h2>
          </div>
          <form className="flex flex-1 flex-col gap-3 p-5" onSubmit={handleCapture}>
            <Textarea
              value={captureText}
              onChange={(event) => setCaptureText(event.target.value)}
              className="min-h-[190px] resize-none"
              placeholder="Remember that Archivum should stay human-centered, review durable memory, and explain provenance."
              aria-label="Capture memory"
            />
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={distillAfterCapture}
                onChange={(event) => setDistillAfterCapture(event.target.checked)}
                className="h-4 w-4 accent-violet-500"
              />
              Propose durable memory updates after capture
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" disabled={saving || captureText.trim().length === 0}>
                <Send className="h-4 w-4" />
                {saving ? 'Capturing...' : 'Capture'}
              </Button>
              <Badge>raw first</Badge>
              <Badge>review gated</Badge>
              <Badge>agent budgeted</Badge>
            </div>
            {status && <p className="text-sm text-emerald-300">{status}</p>}
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="soft-border rounded-[8px] border bg-black/10 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                Librarian response
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Raw capture is saved immediately. Durable memory stays review-gated, cited, scoped, and agent-visible only after approval.
              </p>
            </div>
          </form>
        </section>

        <section className="workspace-pane overflow-hidden">
          <div className="subtle-divider border-b px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Current active context</h2>
          </div>
          <div className="space-y-3 p-5">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Network className="h-4 w-4 text-zinc-500" />
              <span>{context?.nodes.length ?? 0} nodes near {HOME_SCOPE}</span>
            </div>
            {(context?.nodes ?? []).slice(0, 6).map((node) => (
              <div key={node.id} className="soft-border rounded-[8px] border bg-white/[0.03] px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium text-foreground">{node.label}</p>
                  <Badge>{node.node_type}</Badge>
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">{node.id}</p>
              </div>
            ))}
            {context?.reason && (
              <p className="flex items-start gap-2 text-xs text-muted-foreground">
                <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {context.reason}
              </p>
            )}
            <div className="soft-border rounded-[8px] border bg-black/10 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                Context explanations
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {Object.keys(context?.inclusion_explanations ?? {}).length} included ·{' '}
                {Object.keys(context?.exclusion_explanations ?? {}).length} excluded by budget or trust
              </p>
            </div>
            <div className="soft-border rounded-[8px] border bg-black/10 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                Staleness warnings
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {Object.values(context?.staleness_warnings ?? {})[0] ?? 'No stale context flagged.'}
              </p>
            </div>
          </div>
        </section>

        <section className="workspace-pane overflow-hidden">
          <div className="subtle-divider flex items-center justify-between border-b px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Suggested updates</h2>
            <Badge>{suggestions.length} pending</Badge>
          </div>
          <div className="space-y-3 p-5">
            {suggestions.slice(0, 5).map((suggestion) => (
              <div key={suggestion.id} className="soft-border rounded-[8px] border bg-white/[0.03] px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium text-foreground">{suggestion.suggestion_type}</p>
                  <Badge>{suggestion.status}</Badge>
                </div>
                <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">
                  {suggestion.proposed_markdown || suggestion.target_id}
                </p>
                <p className="mt-2 text-xs text-zinc-500">{suggestion.citations.length} source citations</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => handleReviewAction(suggestion, 'accept')}>
                    Accept
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleReviewAction(suggestion, 'keep_both')}>
                    Keep both
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => handleReviewAction(suggestion, 'reject')}>
                    Reject
                  </Button>
                  <Link
                    to="/review"
                    className="text-xs font-medium text-violet-300 underline-offset-2 hover:underline"
                  >
                    Edit, merge &amp; scope in Review
                  </Link>
                </div>
              </div>
            ))}
            {suggestions.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No pending suggestions. Captures can become review cards before they enter durable memory.
              </p>
            )}
          </div>
        </section>

        <section className="workspace-pane overflow-hidden">
          <div className="subtle-divider flex items-center justify-between border-b px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Accepted memory</h2>
            <Archive className="h-4 w-4 text-zinc-500" />
          </div>
          <div className="space-y-3 p-5">
            {activeAssets.map((asset) => (
              <div key={asset.id} className="soft-border rounded-[8px] border bg-white/[0.03] px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium text-foreground">{asset.name}</p>
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-300" />
                </div>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
                  {asset.summary || asset.body || asset.id}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge>{asset.asset_type}</Badge>
                  <Badge>{asset.scope}</Badge>
                  <Badge>{asset.citations.length} cited</Badge>
                </div>
              </div>
            ))}
            {activeAssets.length === 0 && (
              <p className="flex items-start gap-2 text-sm text-muted-foreground">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
                Accepted memory appears here after review.
              </p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
