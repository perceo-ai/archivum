import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Archive,
  Bot,
  CheckCircle2,
  CircleAlert,
  FilePlus2,
  Headphones,
  Network,
  RefreshCw,
  Search,
  Send,
  Settings,
  Sparkles,
  Upload,
} from 'lucide-react';
import {
  captureConversation,
  distillSource,
  getAudioSupport,
  getContextPackage,
  getLlmSettings,
  getMcpSettings,
  listMemoryAssets,
  listSuggestions,
  reviewSuggestion,
  type AudioSupportStatus,
  type ContextPackage,
  type DistillReport,
  type LlmSettings,
  type McpSettings,
  type MemoryAsset,
  type MemorySuggestion,
  type SuggestionReviewAction,
} from '../api';
import type { Page } from '../types';
import { useAppDispatch, useAppState } from '../store';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import QueryPanel from '../components/QueryPanel';
import { Textarea } from '../components/ui/Textarea';

const HOME_SCOPE = 'person:self';

type SetupSnapshot = {
  audio: AudioSupportStatus | null;
  llm: LlmSettings | null;
  mcp: McpSettings | null;
};

type HomeData = {
  suggestions: MemorySuggestion[];
  assets: MemoryAsset[];
  context: ContextPackage | null;
  setup: SetupSnapshot;
};

const emptySetup: SetupSnapshot = {
  audio: null,
  llm: null,
  mcp: null,
};

function librarianSummary(report: DistillReport): string {
  const parts = [
    `Scanned ${report.sentences_scanned} sentence${report.sentences_scanned === 1 ? '' : 's'}`,
    `created ${report.atoms_pending_review} review item${report.atoms_pending_review === 1 ? '' : 's'}`,
  ];
  if (report.conflicts_flagged > 0) {
    parts.push(`flagged ${report.conflicts_flagged} possible conflict${report.conflicts_flagged === 1 ? '' : 's'}`);
  }
  return `${parts.join(', ')}.`;
}

function relativeTime(iso: string): string {
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return 'recently';
  const diff = Date.now() - time;
  const minutes = Math.max(1, Math.round(diff / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function pageExcerpt(page: Page): string {
  const text = page.content
    .replace(/^---[\s\S]*?---/, '')
    .replace(/[#>*_`[\]()]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  return text || 'Blank note';
}

function setupStatus(setup: SetupSnapshot) {
  const modelLabel = setup.llm
    ? `${setup.llm.llm_synthesis_provider} · ${setup.llm.llm_synthesis_model || 'model not set'}`
    : 'Checking model settings';
  const mcpLabel = setup.mcp
    ? setup.mcp.auth_required
      ? 'Agent access secured'
      : 'Agent access open'
    : 'Checking agent access';
  const audioLabel = setup.audio
    ? setup.audio.video_available
      ? 'Audio/video ready'
      : setup.audio.audio_available
        ? 'Audio ready'
        : 'Media transcription off'
    : 'Checking media ingest';

  return { modelLabel, mcpLabel, audioLabel };
}

export default function HomePage() {
  const dispatch = useAppDispatch();
  const { pages } = useAppState();
  const [captureText, setCaptureText] = useState('');
  const [saving, setSaving] = useState(false);
  const [distillAfterCapture, setDistillAfterCapture] = useState(true);
  const [homeData, setHomeData] = useState<HomeData>({
    suggestions: [],
    assets: [],
    context: null,
    setup: emptySetup,
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshHome() {
    setError(null);
    const [
      suggestionsResult,
      assetsResult,
      contextResult,
      audioResult,
      llmResult,
      mcpResult,
    ] = await Promise.allSettled([
      listSuggestions(),
      listMemoryAssets({ status: 'active' }),
      getContextPackage({ scope: HOME_SCOPE, seed_ids: [HOME_SCOPE], depth: 1, max_nodes: 12 }),
      getAudioSupport(),
      getLlmSettings(),
      getMcpSettings(),
    ]);

    setHomeData((current) => ({
      suggestions: suggestionsResult.status === 'fulfilled' ? suggestionsResult.value : current.suggestions,
      assets: assetsResult.status === 'fulfilled' ? assetsResult.value : current.assets,
      context: contextResult.status === 'fulfilled' ? contextResult.value : current.context,
      setup: {
        audio: audioResult.status === 'fulfilled' ? audioResult.value : current.setup.audio,
        llm: llmResult.status === 'fulfilled' ? llmResult.value : current.setup.llm,
        mcp: mcpResult.status === 'fulfilled' ? mcpResult.value : current.setup.mcp,
      },
    }));

    const failed = [suggestionsResult, assetsResult, contextResult, audioResult, llmResult, mcpResult]
      .find((result) => result.status === 'rejected');
    if (failed?.status === 'rejected') {
      setError(failed.reason instanceof Error ? failed.reason.message : 'Some home data could not be loaded');
    }
  }

  useEffect(() => {
    refreshHome();
  }, []);

  const recentPages = useMemo(
    () => [...pages].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 5),
    [pages],
  );
  const activeAssets = useMemo(
    () => homeData.assets.filter((asset) => asset.status === 'active').slice(0, 4),
    [homeData.assets],
  );
  const tagsCount = useMemo(
    () => new Set(pages.flatMap((page) => page.tags)).size,
    [pages],
  );
  const wordsCount = useMemo(
    () => pages.reduce((sum, page) => sum + page.content.trim().split(/\s+/).filter(Boolean).length, 0),
    [pages],
  );
  const setup = setupStatus(homeData.setup);
  const hasPages = pages.length > 0;

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
          : 'Saved as raw capture.',
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
      setHomeData((current) => ({
        ...current,
        suggestions: current.suggestions.filter((item) => item.id !== updated.id),
      }));
      setStatus(`Review item marked ${updated.status}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update suggestion');
    }
  }

  return (
    <div className="page-frame bg-transparent">
      <div className="page-header">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="min-w-0 flex-1">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Start here
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">Today in Archivum</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Use AI to draft, query, organize, and save useful knowledge into the vault.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={openSearch}>
              <Search className="h-4 w-4" />
              Open search
            </Button>
            <Button type="button" variant="outline" onClick={refreshHome}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto">
        <section className="workspace-pane flex min-h-[520px] flex-col overflow-hidden">
          <div className="subtle-divider flex flex-col gap-2 border-b px-5 py-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-foreground">AI Workbench</h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Ask for a cited answer, draft a page, turn context into structure, then save the result into the vault.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary">{setup.modelLabel}</Badge>
              <Badge variant="secondary">save as page</Badge>
            </div>
          </div>
          <div className="min-h-0 flex-1">
            <QueryPanel />
          </div>
        </section>

        <section className="workspace-pane xl:col-span-2">
          <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-4">
            <QuickAction
              to="/tools/ingest"
              icon={<Upload className="h-4 w-4" />}
              title="Import"
              body="Files, folders, archives, URLs, code, email, and media when enabled."
            />
            <QuickAction
              to="/wiki/inbox/quick-note"
              icon={<FilePlus2 className="h-4 w-4" />}
              title="Write"
              body="Open a markdown note and connect ideas with wikilinks."
            />
            <button
              type="button"
              onClick={openSearch}
              className="soft-border rounded-[8px] border bg-white/[0.035] p-4 text-left transition-colors hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Search className="mb-3 h-4 w-4 text-primary" />
              <p className="text-sm font-medium text-foreground">Ask</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">Search notes or ask a cited question without leaving Home.</p>
            </button>
            <QuickAction
              to={homeData.suggestions.length > 0 ? '/review' : '/tools/settings'}
              icon={homeData.suggestions.length > 0 ? <CheckCircle2 className="h-4 w-4" /> : <Settings className="h-4 w-4" />}
              title={homeData.suggestions.length > 0 ? 'Review' : 'Setup'}
              body={homeData.suggestions.length > 0 ? 'Approve or reject suggested memory before it becomes active.' : 'Check models, agent access, media ingest, and sharing.'}
            />
          </div>
        </section>

        {!hasPages && (
          <section className="workspace-pane xl:col-span-2">
            <div className="subtle-divider border-b px-5 py-4">
              <h2 className="text-sm font-semibold text-foreground">Start your vault</h2>
            </div>
            <div className="grid gap-3 p-5 md:grid-cols-3">
              <SetupStep number="1" title="Import a source" body="Start with a doc, URL, repo note, export, or archive." to="/tools/ingest" />
              <SetupStep number="2" title="Write the first note" body="Create a home base for what you want this vault to remember." to="/wiki/inbox/first-note" />
              <SetupStep number="3" title="Connect agents" body="Copy the MCP config from Settings when you are ready." to="/tools/settings" />
            </div>
          </section>
        )}

        <section className="workspace-pane overflow-hidden">
          <div className="subtle-divider flex items-center justify-between border-b px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Vault Snapshot</h2>
            <Badge variant="secondary">{pages.length} pages</Badge>
          </div>
          <div className="grid gap-3 p-5 sm:grid-cols-3">
            <Metric label="Notes" value={pages.length.toLocaleString()} />
            <Metric label="Tags" value={tagsCount.toLocaleString()} />
            <Metric label="Words" value={wordsCount.toLocaleString()} />
          </div>
          <div className="space-y-2 px-5 pb-5">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Recent pages</h3>
            {recentPages.map((page) => (
              <Link
                key={page.slug}
                to={`/wiki/${page.slug}`}
                className="soft-border block rounded-[8px] border bg-white/[0.03] px-3 py-2 transition-colors hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-medium text-foreground">{page.title || page.slug}</p>
                  <span className="shrink-0 text-xs text-zinc-500">{relativeTime(page.updated_at)}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{pageExcerpt(page)}</p>
              </Link>
            ))}
            {recentPages.length === 0 && (
              <p className="text-sm text-muted-foreground">No pages yet. Import a source or write the first note.</p>
            )}
          </div>
        </section>

        <section className="workspace-pane overflow-hidden">
          <div className="subtle-divider flex items-center justify-between border-b px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Setup Status</h2>
            <Link to="/tools/settings" className="text-xs font-medium text-primary underline-offset-2 hover:underline">
              Settings
            </Link>
          </div>
          <div className="space-y-3 p-5">
            <StatusRow icon={<Bot className="h-4 w-4" />} label="Answer model" value={setup.modelLabel} ready={Boolean(homeData.setup.llm?.llm_synthesis_model)} />
            <StatusRow icon={<Network className="h-4 w-4" />} label="Agent access" value={setup.mcpLabel} ready={Boolean(homeData.setup.mcp)} />
            <StatusRow icon={<Headphones className="h-4 w-4" />} label="Media ingest" value={setup.audioLabel} ready={Boolean(homeData.setup.audio?.audio_available)} />
            <p className="text-xs leading-5 text-muted-foreground">
              Settings is where optional capabilities are enabled. Home only shows whether they are ready for day-to-day use.
            </p>
          </div>
        </section>

        <section className="workspace-pane flex min-h-[340px] flex-col overflow-hidden">
          <div className="subtle-divider border-b px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Quick Capture</h2>
          </div>
          <form className="flex flex-1 flex-col gap-3 p-5" onSubmit={handleCapture}>
            <Textarea
              value={captureText}
              onChange={(event) => setCaptureText(event.target.value)}
              className="min-h-[160px] resize-none"
              placeholder="Paste a decision, preference, project note, or context you want saved for later review."
              aria-label="Capture memory"
            />
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={distillAfterCapture}
                onChange={(event) => setDistillAfterCapture(event.target.checked)}
                className="h-4 w-4 accent-primary"
              />
              Turn this into reviewable memory suggestions
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" disabled={saving || captureText.trim().length === 0}>
                <Send className="h-4 w-4" />
                {saving ? 'Saving...' : 'Save capture'}
              </Button>
              <Badge variant="secondary">saved first</Badge>
              <Badge variant="secondary">review required</Badge>
            </div>
            {status && <p className="text-sm text-emerald-300">{status}</p>}
            {error && <p className="text-sm text-destructive">{error}</p>}
          </form>
        </section>

        <section className="workspace-pane overflow-hidden">
          <div className="subtle-divider flex items-center justify-between border-b px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Review Queue</h2>
            <Badge variant={homeData.suggestions.length > 0 ? 'warning' : 'secondary'}>
              {homeData.suggestions.length} pending
            </Badge>
          </div>
          <div className="space-y-3 p-5">
            {homeData.suggestions.slice(0, 4).map((suggestion) => (
              <div key={suggestion.id} className="soft-border rounded-[8px] border bg-white/[0.03] px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium text-foreground">{suggestion.suggestion_type.replace(/_/g, ' ')}</p>
                  <Badge variant="secondary">{suggestion.citations.length} cited</Badge>
                </div>
                <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">
                  {suggestion.proposed_markdown || suggestion.rationale || 'Review this suggested memory update.'}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => handleReviewAction(suggestion, 'accept')}>
                    Accept
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => handleReviewAction(suggestion, 'reject')}>
                    Reject
                  </Button>
                  <Link
                    to="/review"
                    className="text-xs font-medium text-primary underline-offset-2 hover:underline"
                  >
                    Open review
                  </Link>
                </div>
              </div>
            ))}
            {homeData.suggestions.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No pending suggestions. Captures and ingested sources create review cards when there is useful context to approve.
              </p>
            )}
          </div>
        </section>

        <section className="workspace-pane overflow-hidden xl:col-span-2">
          <div className="subtle-divider flex items-center justify-between border-b px-5 py-4">
            <h2 className="text-sm font-semibold text-foreground">Agent Memory</h2>
            <Link to="/tools/memory" className="text-xs font-medium text-primary underline-offset-2 hover:underline">
              Manage
            </Link>
          </div>
          <div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-4">
            {activeAssets.map((asset) => (
              <div key={asset.id} className="soft-border rounded-[8px] border bg-white/[0.03] px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium text-foreground">{asset.name}</p>
                  <Archive className="h-4 w-4 shrink-0 text-emerald-300" />
                </div>
                <p className="mt-1 line-clamp-3 text-xs leading-5 text-muted-foreground">
                  {asset.summary || asset.body || 'Approved memory available to agents.'}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge variant="secondary">{asset.asset_type}</Badge>
                  <Badge variant="secondary">{asset.citations.length} citations</Badge>
                </div>
              </div>
            ))}
            {activeAssets.length === 0 && (
              <p className="flex items-start gap-2 text-sm text-muted-foreground">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
                Approved memory appears here after review.
              </p>
            )}
            {homeData.context?.reason && (
              <p className="flex items-start gap-2 text-sm text-muted-foreground">
                <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
                {homeData.context.reason}
              </p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function QuickAction({
  to,
  icon,
  title,
  body,
}: {
  to: string;
  icon: ReactNode;
  title: string;
  body: string;
}) {
  return (
    <Link
      to={to}
      className="soft-border rounded-[8px] border bg-white/[0.035] p-4 transition-colors hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="mb-3 block text-primary">{icon}</span>
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{body}</p>
    </Link>
  );
}

function SetupStep({
  number,
  title,
  body,
  to,
}: {
  number: string;
  title: string;
  body: string;
  to: string;
}) {
  return (
    <Link
      to={to}
      className="soft-border rounded-[8px] border bg-white/[0.035] p-4 transition-colors hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="mb-3 flex h-7 w-7 items-center justify-center rounded-[6px] bg-primary/20 text-xs font-semibold text-primary">
        {number}
      </div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{body}</p>
    </Link>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="soft-border rounded-[8px] border bg-black/10 px-3 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

function StatusRow({
  icon,
  label,
  value,
  ready,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  ready: boolean;
}) {
  return (
    <div className="soft-border flex items-start gap-3 rounded-[8px] border bg-white/[0.03] px-3 py-2">
      <span className={ready ? 'mt-0.5 text-emerald-300' : 'mt-0.5 text-zinc-500'}>{icon}</span>
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{value}</p>
      </div>
    </div>
  );
}
