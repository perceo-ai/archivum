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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/DropdownMenu';
import { useToast } from '../components/ui/Toast';
import { Download, MoreHorizontal, Share2, Trash2 } from 'lucide-react';

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
    <div className="flex flex-col h-full">
      {/* Title bar */}
      <div
        className="shrink-0 border-b border-border px-4 py-3 bg-panel/70 backdrop-blur supports-[backdrop-filter]:bg-panel/50"
      >
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <Input
              value={titleDraft}
              onChange={(e) => {
                setTitleDraft(e.target.value);
                scheduleMetaSave({ title: e.target.value });
              }}
              placeholder={loading ? 'Loading…' : 'Untitled'}
              className="h-9 text-sm font-semibold"
              aria-label="Page title"
            />
            <div className="mt-2 flex items-center gap-2">
              <Input
                value={tagsDraft}
                onChange={(e) => {
                  setTagsDraft(e.target.value);
                  scheduleMetaSave({ tags: e.target.value.split(',').map((t) => t.trim()).filter(Boolean) });
                }}
                placeholder="tags (comma separated)"
                className="h-8 text-xs max-w-md"
                aria-label="Tags"
              />
              {page?.authored_by === 'agent' && <Badge variant="info">AI</Badge>}
              {parsedTags.slice(0, 3).map((t) => (
                <Badge key={t} className="hidden sm:inline-flex">
                  {t}
                </Badge>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button variant="secondary" size="sm" onClick={handleSaveNow} disabled={!page}>
              Save
            </Button>
            <PageMenu
              slug={slugStr}
              disabled={!page}
              shareLoading={shareLoading}
              onShare={handleShare}
              onDelete={() => setDeleteOpen(true)}
            />
          </div>
        </div>
        {error && <div className="text-xs text-red-400 mt-1">{error}</div>}
      </div>

      {/* Editor */}
      <div className="flex-1 overflow-hidden">
        {loading && !page && (
          <div className="p-6 space-y-2">
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

function PageMenu({
  slug,
  disabled,
  shareLoading,
  onShare,
  onDelete,
}: {
  slug: string;
  disabled: boolean;
  shareLoading: boolean;
  onShare: () => void;
  onDelete: () => void;
}) {
  function handleExport(format: 'html' | 'pdf') {
    window.open(`/api/export?slug=${encodeURIComponent(slug)}&format=${format}`, '_blank');
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" disabled={disabled} aria-label="Page actions">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onShare} disabled={shareLoading}>
          <Share2 className="h-4 w-4" />
          {shareLoading ? 'Sharing...' : 'Share'}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => handleExport('html')}>
          <Download className="h-4 w-4" />
          Export HTML
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => handleExport('pdf')}>
          <Download className="h-4 w-4" />
          Export PDF
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onDelete} className="text-destructive">
          <Trash2 className="h-4 w-4" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
