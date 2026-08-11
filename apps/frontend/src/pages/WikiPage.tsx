import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAppDispatch } from '../store';
import { createShareLink, deletePage, getPage, listPages, updatePage } from '../api';
import type { Page } from '../types';
import Editor, { type EditorHandle } from '../components/Editor/Editor';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { Dialog } from '../components/ui/Dialog';
import { useToast } from '../components/ui/Toast';
import PageActions from '../components/PageActions';

export default function WikiPage() {
  const params = useParams();
  const slug = params['*'];
  const dispatch = useAppDispatch();
  const { push } = useToast();
  const [page, setPage] = useState<Page | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [tagsDraft, setTagsDraft] = useState('');
  const [contentDraft, setContentDraft] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const editorRef = useRef<EditorHandle | null>(null);
  const metaSaveTimer = useRef<ReturnType<typeof setTimeout>>();

  const parsedTags = useMemo(() => {
    return tagsDraft
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
  }, [tagsDraft]);

  useEffect(() => {
    if (!slug) return;
    dispatch({ type: 'SET_CURRENT_SLUG', slug });
    setLoading(true);
    setError(null);
    getPage(slug)
      .then((p) => {
        setPage(p);
        setTitleDraft(p.title ?? '');
        setTagsDraft((p.tags ?? []).join(', '));
        setContentDraft(null);
        dispatch({ type: 'UPSERT_PAGE', page: p });
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [slug, dispatch]);

  // Reset share URL when navigating to a different page
  useEffect(() => {
    setShareUrl(null);
    setShareDialogOpen(false);
  }, [slug]);

  if (!slug) return null;
  const slugStr = slug;

  function scheduleMetaSave(next: { title?: string; tags?: string[] }) {
    clearTimeout(metaSaveTimer.current);
    metaSaveTimer.current = setTimeout(async () => {
      dispatch({ type: 'SET_SAVE_STATUS', status: 'saving' });
      try {
        const updated = await updatePage(slugStr, {
          title: next.title ?? titleDraft,
          tags: next.tags ?? parsedTags,
        });
        setPage(updated);
        dispatch({ type: 'UPSERT_PAGE', page: updated });
        dispatch({ type: 'SET_SAVE_STATUS', status: 'saved' });
      } catch (e) {
        dispatch({ type: 'SET_SAVE_STATUS', status: 'error' });
        setError((e as Error).message);
      }
    }, 650);
  }

  async function handleSaveNow() {
    dispatch({ type: 'SET_SAVE_STATUS', status: 'saving' });
    try {
      const content = contentDraft ?? editorRef.current?.getContent() ?? page?.content ?? '';
      const updated = await updatePage(slugStr, { title: titleDraft, tags: parsedTags, content });
      setPage(updated);
      setContentDraft(null);
      dispatch({ type: 'UPSERT_PAGE', page: updated });
      dispatch({ type: 'SET_SAVE_STATUS', status: 'saved' });
      push({ kind: 'success', title: 'Saved', description: updated.title });
    } catch (e) {
      dispatch({ type: 'SET_SAVE_STATUS', status: 'error' });
      setError((e as Error).message);
      push({ kind: 'error', title: 'Save failed', description: (e as Error).message });
    }
  }

  async function handleDelete() {
    if (!page) return;
    dispatch({ type: 'SET_SAVE_STATUS', status: 'saving' });
    try {
      await deletePage(page.slug);
      dispatch({ type: 'DELETE_PAGE', slug: page.slug });
      push({ kind: 'success', title: 'Deleted page', description: page.title });
      setDeleteOpen(false);
      // Pick a next page if available; otherwise go to ingest
      const pages = await listPages().catch(() => null);
      if (pages && pages.length > 0) {
        dispatch({ type: 'SET_PAGES', pages });
        window.location.assign(`/wiki/${pages[0].slug}`);
      } else {
        window.location.assign('/ingest');
      }
    } catch (e) {
      dispatch({ type: 'SET_SAVE_STATUS', status: 'error' });
      setError((e as Error).message);
      push({ kind: 'error', title: 'Delete failed', description: (e as Error).message });
    }
  }

  async function handleShare() {
    if (shareUrl) {
      setShareDialogOpen(true);
      return;
    }
    setShareLoading(true);
    try {
      const result = await createShareLink({ type: 'page', target_id: slugStr });
      const fullUrl = window.location.origin + result.url;
      setShareUrl(fullUrl);
      setShareDialogOpen(true);
    } catch (e) {
      push({ kind: 'error', title: 'Share failed', description: (e as Error).message });
    } finally {
      setShareLoading(false);
    }
  }

  async function handleCopyShareUrl() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      push({ kind: 'success', title: 'Copied', description: 'Share link copied to clipboard' });
    } catch {
      push({ kind: 'error', title: 'Copy failed', description: 'Could not write to clipboard' });
    }
  }

  return (
    <div className="page-frame !max-w-none bg-transparent">
      <div className="page-header shrink-0">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Library
            </p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="font-mono">{slugStr}</span>
              {page?.authored_by === 'agent' && <Badge variant="info">AI-authored</Badge>}
            </div>
            <Input
              value={titleDraft}
              onChange={(e) => {
                setTitleDraft(e.target.value);
                scheduleMetaSave({ title: e.target.value });
              }}
              placeholder={loading ? 'Loading…' : 'Untitled'}
              className="mt-3 h-12 border-0 bg-transparent px-0 text-3xl font-semibold tracking-tight shadow-none focus-visible:ring-0"
              aria-label="Page title"
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Input
                value={tagsDraft}
                onChange={(e) => {
                  setTagsDraft(e.target.value);
                  scheduleMetaSave({ tags: e.target.value.split(',').map((t) => t.trim()).filter(Boolean) });
                }}
                placeholder="tags, comma separated"
                className="h-9 max-w-md rounded-2xl border-border/80 bg-background/70 text-sm"
                aria-label="Tags"
              />
              {parsedTags.slice(0, 4).map((t) => (
                <Badge key={t} className="bg-accent/70 text-accent-foreground">
                  {t}
                </Badge>
              ))}
            </div>
          </div>
          <div className="flex shrink-0 items-center">
            <PageActions
              slug={slugStr}
              disabled={!page}
              shareLoading={shareLoading}
              onSave={handleSaveNow}
              onShare={handleShare}
              onDelete={() => setDeleteOpen(true)}
            />
          </div>
        </div>
        {error && <div className="mt-3 text-xs text-destructive">{error}</div>}
      </div>

      <div className="surface-panel flex min-h-0 flex-1 overflow-hidden rounded-[28px]">
        {loading && !page && (
          <div className="space-y-2 p-6">
            <div className="skeleton h-4 w-full" />
            <div className="skeleton h-4 w-5/6" />
            <div className="skeleton h-4 w-4/5" />
          </div>
        )}

        {page && (
          <Editor
            ref={editorRef}
            slug={page.slug}
            initialContent={page.content}
            onSave={(s) => dispatch({ type: 'SET_SAVE_STATUS', status: s })}
            onChange={(c) => setContentDraft(c)}
          />
        )}
      </div>

      <Dialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete this page?"
        description="This will remove the markdown file and delete it from the index."
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              Delete
            </Button>
          </div>
        }
      />

      <Dialog
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        title="Share link"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" onClick={() => setShareDialogOpen(false)}>
              Close
            </Button>
            <Button variant="secondary" onClick={handleCopyShareUrl} disabled={!shareUrl}>
              Copy
            </Button>
          </div>
        }
      >
        {shareUrl && (
          <input
            readOnly
            value={shareUrl}
            className="w-full rounded-md border border-input bg-background px-2 py-2 text-xs text-foreground font-mono truncate focus:outline-none"
            onClick={(e) => (e.target as HTMLInputElement).select()}
          />
        )}
      </Dialog>
    </div>
  );
}
