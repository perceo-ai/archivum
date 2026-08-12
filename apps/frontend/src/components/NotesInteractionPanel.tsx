import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Copy, ExternalLink, Pencil } from 'lucide-react';
import { useAppDispatch, useAppState } from '../store';
import { getPage, updatePage } from '../api';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { Dialog } from './ui/Dialog';

function parseTags(input: string): string[] {
  return input
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

export default function NotesInteractionPanel() {
  const { currentSlug } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const [editOpen, setEditOpen] = useState(false);
  const [editSlug, setEditSlug] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editTags, setEditTags] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const editTagsParsed = useMemo(() => parseTags(editTags), [editTags]);

  async function openEdit(slug: string) {
    setEditError(null);
    setEditSlug(slug);
    setEditOpen(true);
    setEditSaving(false);

    try {
      const p = await getPage(slug);
      setEditTitle(p.title ?? '');
      setEditTags((p.tags ?? []).join(', '));
    } catch (err) {
      setEditError((err as Error).message);
    }
  }

  async function handleEditSave() {
    if (!editSlug) return;
    setEditSaving(true);
    setEditError(null);
    try {
      const updated = await updatePage(editSlug, {
        title: editTitle.trim() || null,
        tags: editTagsParsed,
      });
      dispatch({ type: 'UPSERT_PAGE', page: updated });
      setEditOpen(false);

      // Force refresh for the editor view if we updated the active page.
      if (currentSlug === updated.slug) {
        window.location.assign(`/wiki/${updated.slug}`);
      } else {
        navigate(`/wiki/${updated.slug}`);
      }
    } catch (err) {
      setEditError((err as Error).message);
    } finally {
      setEditSaving(false);
    }
  }

  function openCurrentPage() {
    if (currentSlug) navigate(`/wiki/${currentSlug}`);
  }

  async function copyLink(slug: string) {
    const url = `${window.location.origin}/wiki/${slug}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // best-effort fallback: silently no-op
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={openCurrentPage}
          disabled={!currentSlug}
          className="w-full justify-start"
        >
          <ExternalLink className="h-4 w-4" />
          Open page
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => currentSlug && openEdit(currentSlug)}
          disabled={!currentSlug}
          className="w-full justify-start"
        >
          <Pencil className="h-4 w-4" />
          Edit title and tags
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => currentSlug && copyLink(currentSlug)}
          disabled={!currentSlug}
          className="w-full justify-start"
        >
          <Copy className="h-4 w-4" />
          Copy page link
        </Button>
      </div>

      {!currentSlug && (
        <div className="mt-4 text-xs leading-5 text-muted-foreground">
          Open a note to edit metadata or copy its link.
        </div>
      )}

      <Dialog
        open={editOpen}
        onOpenChange={(o) => {
          setEditOpen(o);
          if (!o) setEditSlug(null);
        }}
        title="Quick edit"
        description={editSlug ? `Editing ${editSlug}` : 'Editing'}
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditOpen(false)} disabled={editSaving}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleEditSave} disabled={editSaving || !editSlug}>
              {editSaving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          <div>
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Title</div>
            <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} placeholder="Title" />
          </div>
          <div>
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Tags</div>
            <Input
              value={editTags}
              onChange={(e) => setEditTags(e.target.value)}
              placeholder="comma, separated, tags"
            />
          </div>
          {editError && <div className="text-xs text-red-400">{editError}</div>}
        </div>
      </Dialog>
    </div>
  );
}
