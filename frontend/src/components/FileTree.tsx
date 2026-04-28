import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppState, useAppDispatch } from '../store';
import { createPage, ingestFile } from '../api';
import type { IngestProgress } from '../types';

export default function FileTree() {
  const { pages, currentSlug } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [filter, setFilter] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sorted = [...pages].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );

  const filtered = filter.trim()
    ? sorted.filter(
        (p) =>
          p.title.toLowerCase().includes(filter.toLowerCase()) ||
          p.slug.toLowerCase().includes(filter.toLowerCase()),
      )
    : sorted;

  async function handleCreatePage() {
    if (!newTitle.trim()) return;
    const slug = newTitle
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '');
    try {
      const page = await createPage(slug, newTitle.trim(), `# ${newTitle.trim()}\n\n`);
      dispatch({ type: 'UPSERT_PAGE', page });
      setCreating(false);
      setNewTitle('');
      navigate(`/wiki/${page.slug}`);
    } catch (err) {
      console.error('Failed to create page:', err);
    }
  }

  async function handleFileDrop(files: FileList) {
    for (const file of Array.from(files)) {
      try {
        const events: IngestProgress[] = [];
        await ingestFile(file, (progress) => {
          events.push(progress);
          if (progress.type === 'page_created' || progress.type === 'page_updated') {
            // Reload pages list after ingest
          }
        });
        // Refresh pages
        const { listPages } = await import('../api');
        const updatedPages = await listPages();
        dispatch({ type: 'SET_PAGES', pages: updatedPages });
      } catch (err) {
        console.error('Ingest failed:', err);
      }
    }
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(true);
  }

  function onDragLeave() {
    setDragOver(false);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      handleFileDrop(e.dataTransfer.files);
    }
  }

  return (
    <div
      className="flex flex-col h-full"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      style={{ outline: dragOver ? '2px dashed #4B91F1' : 'none' }}
    >
      {/* Header */}
      <div className="px-3 py-2 border-b shrink-0" style={{ borderColor: '#3a3a4a' }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
            Pages
          </span>
          <button
            onClick={() => setCreating(true)}
            className="text-text-muted hover:text-accent transition-colors"
            title="New page"
          >
            <PlusIcon />
          </button>
        </div>
        <input
          type="text"
          placeholder="Filter pages..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full bg-transparent border rounded px-2 py-1 text-xs text-text-secondary placeholder-text-muted focus:outline-none focus:border-accent/50"
          style={{ borderColor: '#3a3a4a' }}
        />
      </div>

      {/* New page input */}
      {creating && (
        <div className="px-3 py-2 border-b" style={{ borderColor: '#3a3a4a' }}>
          <input
            type="text"
            placeholder="Page title..."
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreatePage();
              if (e.key === 'Escape') {
                setCreating(false);
                setNewTitle('');
              }
            }}
            autoFocus
            className="w-full bg-transparent border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            style={{ borderColor: '#4B91F1' }}
          />
          <div className="flex gap-1 mt-1">
            <button
              onClick={handleCreatePage}
              className="text-xs text-accent hover:text-accent/80 transition-colors"
            >
              Create
            </button>
            <span className="text-text-muted text-xs">·</span>
            <button
              onClick={() => {
                setCreating(false);
                setNewTitle('');
              }}
              className="text-xs text-text-muted hover:text-text-secondary transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Pages list */}
      <div className="flex-1 overflow-y-auto py-1">
        {filtered.length === 0 && (
          <div className="px-3 py-4 text-center text-text-muted text-xs">
            {filter ? 'No matches' : 'No pages yet'}
          </div>
        )}
        {filtered.map((page) => (
          <button
            key={page.slug}
            onClick={() => navigate(`/wiki/${page.slug}`)}
            className={`w-full text-left px-3 py-2 text-sm transition-colors flex items-start gap-2 group ${
              currentSlug === page.slug
                ? 'bg-accent/10 text-text-primary'
                : 'text-text-secondary hover:bg-white/5 hover:text-text-primary'
            }`}
          >
            <span className="flex-1 truncate leading-snug">{page.title}</span>
            {page.authored_by === 'agent' && (
              <span className="shrink-0 text-xs px-1 py-0.5 rounded text-accent/70 border border-accent/30 leading-none mt-0.5">
                AI
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Drop hint */}
      <div
        className="px-3 py-2 border-t text-xs text-text-muted text-center shrink-0"
        style={{ borderColor: '#3a3a4a' }}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        style={{ borderColor: '#3a3a4a', cursor: 'pointer' }}
      >
        Drop files to ingest
      </div>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => e.target.files && handleFileDrop(e.target.files)}
      />
    </div>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
