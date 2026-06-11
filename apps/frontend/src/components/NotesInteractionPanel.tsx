import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppState } from '../store';
import { getPage, search, updatePage } from '../api';
import type { SearchResult } from '../types';
import { Button } from './ui/Button';
import { Card } from './ui/Card';
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

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [editOpen, setEditOpen] = useState(false);
  const [editSlug, setEditSlug] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editTags, setEditTags] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const editTagsParsed = useMemo(() => parseTags(editTags), [editTags]);

  async function runSearch(e?: React.FormEvent) {
    e?.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await search(query.trim());
      setResults(res);
    } catch (err) {
      setError((err as Error).message);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

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

  async function copyLink(slug: string) {
    const url = `${window.location.origin}/wiki/${slug}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // best-effort fallback: silently no-op
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-border shrink-0">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Notes actions
        </h3>
      </div>

      <div className="px-3 py-2 border-b border-border shrink-0">
        <form onSubmit={runSearch} className="flex gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search notes…"
          />
          <Button type="submit" variant="primary" size="sm" disabled={loading || !query.trim()}>
            {loading ? '…' : 'Search'}
          </Button>
        </form>
      </div>

      <div className="flex-1 overflow-y-auto py-1 px-3">
        {error && <div className="text-xs text-red-400 py-2">{error}</div>}

        {loading && (
          <div className="space-y-2 py-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="skeleton h-20 w-full" />
            ))}
          </div>
        )}

        {!loading && !error && results.length === 0 && query.trim() && (
          <div className="text-xs text-muted-foreground py-6 text-center">No matches.</div>
        )}

        {!loading && results.length > 0 && (
          <div className="space-y-2 pb-3">
            {results.map((r) => (
              <div key={r.slug} className="space-y-2">
                <Card className="p-3 hover:border-accent/30">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-foreground truncate">{r.title}</div>
                      <div className="text-xs text-muted-foreground truncate">{r.slug}</div>
                    </div>
                    <div className="shrink-0">
                      {r.slug === currentSlug ? (
                        <span className="text-xs text-green-400">Active</span>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-text-secondary leading-relaxed line-clamp-3">
                    {r.excerpt}
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => navigate(`/wiki/${r.slug}`)}
                      className="flex-1"
                    >
                      Open
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openEdit(r.slug)}
                      title="Edit title/tags"
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => copyLink(r.slug)}
                      title="Copy link"
                    >
                      Copy
                    </Button>
                  </div>
                </Card>
              </div>
            ))}
          </div>
        )}

        {!loading && !error && !query.trim() && (
          <div className="text-xs text-muted-foreground py-6 text-center">
            Search your wiki to quickly open, edit, or copy links to notes.
          </div>
        )}
      </div>

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
