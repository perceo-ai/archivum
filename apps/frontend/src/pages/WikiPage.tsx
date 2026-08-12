import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Hash, Plus, X } from 'lucide-react';
import { useAppDispatch } from '../store';
import {
  acceptSuggestion,
  createShareLink,
  deletePage,
  getPage,
  listPageSuggestions,
  listPages,
  rejectSuggestion,
  updatePage,
} from '../api';
import type { MemorySuggestion } from '../api';
import type { Page } from '../types';
import Editor, { type EditorHandle } from '../components/Editor/Editor';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { Dialog } from '../components/ui/Dialog';
import { useToast } from '../components/ui/Toast';
import PageActions from '../components/PageActions';
import { addTag, removeTag } from './wikiMetadata';

export default function WikiPage() {
  const params = useParams();
  const slug = params['*'];
  const dispatch = useAppDispatch();
  const { push } = useToast();
  const [page, setPage] = useState<Page | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState('');
  const [tagsDraft, setTagsDraft] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [addingTag, setAddingTag] = useState(false);
  const [contentDraft, setContentDraft] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<MemorySuggestion[]>([]);
  const editorRef = useRef<EditorHandle | null>(null);
  const metaSaveTimer = useRef<ReturnType<typeof setTimeout>>();

  const parsedTags = useMemo(() => {
    return tagsDraft.map((t) => t.trim()).filter(Boolean);
  }, [tagsDraft]);

  useEffect(() => {
    if (!slug) return;
    dispatch({ type: 'SET_CURRENT_SLUG', slug });
    setLoading(true);
    setError(null);
    Promise.all([getPage(slug), listPageSuggestions(slug).catch(() => [])])
      .then(([p, pageSuggestions]) => {
        setPage(p);
        setTitleDraft(p.title ?? '');
        setTagsDraft(p.tags ?? []);
        setTagInput('');
        setAddingTag(false);
        setContentDraft(null);
        setSuggestions(pageSuggestions);
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

  function commitTags(nextTags: string[]) {
    setTagsDraft(nextTags);
    scheduleMetaSave({ tags: nextTags });
  }

  function handleAddTag() {
    const nextTags = addTag(parsedTags, tagInput);
    setTagInput('');
    setAddingTag(false);
    if (nextTags !== parsedTags) commitTags(nextTags);
  }

  function handleRemoveTag(tag: string) {
    commitTags(removeTag(parsedTags, tag));
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

  async function handleAcceptSuggestion(suggestion: MemorySuggestion) {
    try {
      const updated = await acceptSuggestion(suggestion.id);
      setSuggestions((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      push({ kind: 'success', title: 'Suggestion accepted' });
    } catch (e) {
      push({ kind: 'error', title: 'Accept failed', description: (e as Error).message });
    }
  }

  async function handleRejectSuggestion(suggestion: MemorySuggestion) {
    try {
      const updated = await rejectSuggestion(suggestion.id);
      setSuggestions((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      push({ kind: 'success', title: 'Suggestion rejected' });
    } catch (e) {
      push({ kind: 'error', title: 'Reject failed', description: (e as Error).message });
    }
  }

  return (
    <div className="page-frame !max-w-none bg-transparent">
      <div className="page-header shrink-0 px-4 pt-2 md:px-8">
        <div className="flex w-full items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="font-mono text-[11px] text-muted-foreground">
                {slugStr}
              </span>
              {page?.authored_by === 'agent' && <Badge variant="info">AI-authored</Badge>}
            </div>
            <Input
              value={titleDraft}
              onChange={(e) => {
                setTitleDraft(e.target.value);
                scheduleMetaSave({ title: e.target.value });
              }}
              placeholder={loading ? 'Loading…' : 'Untitled'}
              className="mt-3 h-auto min-h-14 border-0 bg-transparent px-0 py-0 text-[34px] font-bold leading-tight tracking-normal text-foreground shadow-none placeholder:text-muted-foreground/60 focus-visible:ring-0 md:text-[42px]"
              aria-label="Page title"
            />
            <div className="mt-4 flex min-h-8 flex-wrap items-center gap-1.5">
              {parsedTags.map((tag) => (
                <span
                  key={tag}
                  className="group inline-flex h-7 items-center gap-1 rounded-[5px] px-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-foreground/[0.05] hover:text-foreground"
                >
                  <Hash className="h-3 w-3" />
                  {tag}
                  <button
                    type="button"
                    onClick={() => handleRemoveTag(tag)}
                    className="ml-0.5 rounded-[4px] p-0.5 opacity-0 transition-opacity hover:bg-foreground/10 hover:text-foreground group-hover:opacity-100"
                    aria-label={`Remove ${tag} tag`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
              {addingTag ? (
                <input
                  autoFocus
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onBlur={handleAddTag}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddTag();
                    }
                    if (e.key === 'Escape') {
                      setTagInput('');
                      setAddingTag(false);
                    }
                  }}
                  placeholder="Tag"
                  className="h-7 w-28 rounded-[5px] border border-transparent bg-transparent px-1.5 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-foreground/15"
                  aria-label="New tag"
                />
              ) : (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setAddingTag(true)}
                  className="h-7 gap-1 rounded-[5px] px-1.5 text-xs text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Tag
                </Button>
              )}
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

      <div className="flex min-h-0 flex-1 overflow-hidden bg-transparent">
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
            pendingSuggestions={suggestions}
            onAcceptSuggestion={handleAcceptSuggestion}
            onRejectSuggestion={handleRejectSuggestion}
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
