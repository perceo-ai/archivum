import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAppDispatch } from '../store';
import { createPage, deletePage, getPage, updatePage } from '../api';
import type { Page } from '../types';
import Editor, { type EditorHandle } from '../components/Editor/Editor';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { Dialog } from '../components/ui/Dialog';
import { useToast } from '../components/ui/Toast';

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
  const [createOpen, setCreateOpen] = useState(false);
  const [createTitle, setCreateTitle] = useState('');
  const [createFolder, setCreateFolder] = useState('');
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
      const { listPages } = await import('../api');
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

  async function handleCreate() {
    if (!createTitle.trim()) return;
    try {
      const folder = slugifyFolder(createFolder);
      const titleSlug = slugifySegment(createTitle) || 'untitled';
      const created = await createPage({
        title: createTitle.trim(),
        slug: folder ? `${folder}/${titleSlug}` : undefined,
        content: `# ${createTitle.trim()}\n\n`,
      });
      dispatch({ type: 'UPSERT_PAGE', page: created });
      push({ kind: 'success', title: 'Created page', description: created.title });
      setCreateOpen(false);
      setCreateTitle('');
      setCreateFolder('');
      window.location.assign(`/wiki/${created.slug}`);
    } catch (e) {
      push({ kind: 'error', title: 'Create failed', description: (e as Error).message });
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
            <Button variant="ghost" size="sm" onClick={() => setCreateOpen(true)}>
              New
            </Button>
            <Button variant="secondary" size="sm" onClick={handleSaveNow} disabled={!page}>
              Save
            </Button>
            <Button variant="danger" size="sm" onClick={() => setDeleteOpen(true)} disabled={!page}>
              Delete
            </Button>
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
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="Create a new page"
        description="Optionally choose a folder — the slug will be generated automatically."
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleCreate} disabled={!createTitle.trim()}>
              Create
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          <Input
            value={createFolder}
            onChange={(e) => setCreateFolder(e.target.value)}
            placeholder="Folder (optional) e.g. work/meetings"
          />
          <Input
            value={createTitle}
            onChange={(e) => setCreateTitle(e.target.value)}
            placeholder="e.g. Retrieval notes"
            autoFocus
          />
        </div>
      </Dialog>
    </div>
  );
}

function slugifySegment(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function slugifyFolder(folder: string): string | undefined {
  const trimmed = folder.trim();
  if (!trimmed) return undefined;
  const normalized = trimmed
    .replace(/^\/+|\/+$/g, '')
    .split('/')
    .map((seg) => slugifySegment(seg))
    .filter(Boolean)
    .join('/');
  return normalized || undefined;
}

