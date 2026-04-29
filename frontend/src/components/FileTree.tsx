import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppState, useAppDispatch } from '../store';
import { createPage, ingestFile } from '../api';
import type { IngestProgress } from '../types';
import { cn } from '../lib/cn';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { Badge } from './ui/Badge';

export default function FileTree() {
  const { pages, currentSlug } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [filter, setFilter] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newFolder, setNewFolder] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
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

  const tree = useMemo(() => buildTree(filtered), [filtered]);
  const autoExpanded = useMemo(() => {
    if (!filter.trim()) return null;
    const set = new Set<string>();
    for (const p of filtered) {
      const parts = p.slug.split('/').slice(0, -1);
      let acc = '';
      for (const part of parts) {
        acc = acc ? `${acc}/${part}` : part;
        set.add(acc);
      }
    }
    return set;
  }, [filter, filtered]);

  async function handleCreatePage() {
    if (!newTitle.trim()) return;
    const titleSlug = slugifySegment(newTitle.trim());
    const folderSlug = slugifyFolder(newFolder.trim());
    const slug = folderSlug ? `${folderSlug}/${titleSlug}` : titleSlug;
    try {
      const page = await createPage({
        slug,
        title: newTitle.trim(),
        content: `# ${newTitle.trim()}\n\n`,
      });
      dispatch({ type: 'UPSERT_PAGE', page });
      setCreating(false);
      setNewTitle('');
      setNewFolder('');
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
      style={{ outline: dragOver ? '2px dashed rgb(var(--accent))' : 'none' }}
    >
      {/* Header */}
      <div className="px-3 py-2 border-b border-border shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Pages
          </span>
          <Button onClick={() => setCreating(true)} variant="ghost" size="icon" title="New page">
            <PlusIcon />
          </Button>
        </div>
        <Input
          type="text"
          placeholder="Filter pages..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-8 text-xs"
        />
      </div>

      {/* New page input */}
      {creating && (
        <div className="px-3 py-2 border-b border-border space-y-2">
          <Input
            type="text"
            placeholder="Folder (optional) e.g. work/meetings"
            value={newFolder}
            onChange={(e) => setNewFolder(e.target.value)}
            className="h-8 text-xs"
          />
          <Input
            type="text"
            placeholder="Page title..."
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreatePage();
              if (e.key === 'Escape') {
                setCreating(false);
                setNewTitle('');
                setNewFolder('');
              }
            }}
            autoFocus
            className="h-8 text-xs"
          />
          <div className="flex items-center gap-2">
            <Button onClick={handleCreatePage} variant="primary" size="sm" disabled={!newTitle.trim()}>
              Create
            </Button>
            <Button
              onClick={() => {
                setCreating(false);
                setNewTitle('');
                setNewFolder('');
              }}
              variant="ghost"
              size="sm"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Pages list */}
      <div className="flex-1 overflow-y-auto py-1">
        {filtered.length === 0 && (
          <div className="px-3 py-4 text-center text-muted-foreground text-xs">
            {filter ? 'No matches' : 'No pages yet'}
          </div>
        )}
        <TreeFolder
          node={tree}
          depth={0}
          currentSlug={currentSlug}
          onToggle={(path) =>
            setExpanded((prev) => {
              const next = new Set(prev);
              if (next.has(path)) next.delete(path);
              else next.add(path);
              return next;
            })
          }
          isExpanded={(path) => (autoExpanded ? autoExpanded.has(path) : expanded.has(path))}
          onNavigate={(s) => navigate(`/wiki/${s}`)}
        />
      </div>

      {/* Drop hint */}
      <div
        className="px-3 py-2 border-t border-border text-xs text-muted-foreground text-center shrink-0"
        onClick={() => fileInputRef.current?.click()}
        role="button"
        style={{ cursor: 'pointer' }}
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

type TreeNode = {
  name: string;
  path: string; // folder path (no leading slash), '' for root
  folders: TreeNode[];
  pages: Array<{ slug: string; title: string; authored_by: 'user' | 'agent' }>;
};

function buildTree(pages: Array<{ slug: string; title: string; authored_by: 'user' | 'agent' }>): TreeNode {
  const root: TreeNode = { name: '', path: '', folders: [], pages: [] };

  const folderIndex = new Map<string, TreeNode>();
  folderIndex.set('', root);

  function ensureFolder(path: string): TreeNode {
    const existing = folderIndex.get(path);
    if (existing) return existing;
    const parts = path.split('/');
    const parentPath = parts.slice(0, -1).join('/');
    const name = parts[parts.length - 1]!;
    const parent = ensureFolder(parentPath);
    const node: TreeNode = { name, path, folders: [], pages: [] };
    parent.folders.push(node);
    folderIndex.set(path, node);
    return node;
  }

  for (const p of pages) {
    const parts = p.slug.split('/');
    const folderPath = parts.slice(0, -1).join('/');
    const folder = ensureFolder(folderPath);
    folder.pages.push({ slug: p.slug, title: p.title, authored_by: p.authored_by });
  }

  function sortNode(node: TreeNode) {
    node.folders.sort((a, b) => a.name.localeCompare(b.name));
    node.pages.sort((a, b) => a.title.localeCompare(b.title));
    node.folders.forEach(sortNode);
  }
  sortNode(root);

  return root;
}

function TreeFolder({
  node,
  depth,
  currentSlug,
  onToggle,
  isExpanded,
  onNavigate,
}: {
  node: TreeNode;
  depth: number;
  currentSlug: string | null;
  onToggle: (path: string) => void;
  isExpanded: (path: string) => boolean;
  onNavigate: (slug: string) => void;
}) {
  const isRoot = node.path === '';
  const expanded = isRoot ? true : isExpanded(node.path);
  const hasChildren = node.folders.length > 0 || node.pages.length > 0;

  return (
    <div>
      {!isRoot && (
        <button
          className={cn(
            'w-full text-left px-2 py-1.5 text-xs transition-colors flex items-center gap-1.5',
            'hover:bg-muted/40 text-muted-foreground hover:text-foreground',
          )}
          style={{ paddingLeft: 8 + depth * 12 }}
          onClick={() => onToggle(node.path)}
        >
          <ChevronIcon open={expanded} />
          <FolderIcon />
          <span className="truncate">{node.name}</span>
          {!hasChildren && <span className="ml-auto text-[11px] text-muted-foreground/70">—</span>}
        </button>
      )}

      {expanded && (
        <div>
          {node.folders.map((f) => (
            <TreeFolder
              key={f.path}
              node={f}
              depth={isRoot ? depth : depth + 1}
              currentSlug={currentSlug}
              onToggle={onToggle}
              isExpanded={isExpanded}
              onNavigate={onNavigate}
            />
          ))}

          {node.pages.map((p) => (
            <button
              key={p.slug}
              onClick={() => onNavigate(p.slug)}
              className={cn(
                'w-full text-left px-2 py-2 text-sm transition-colors flex items-start gap-2 group',
                currentSlug === p.slug
                  ? 'bg-accent/10 text-foreground'
                  : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground',
              )}
              style={{ paddingLeft: 8 + (isRoot ? depth : depth + 1) * 12 }}
            >
              <span className="flex-1 truncate leading-snug">{p.title}</span>
              {p.authored_by === 'agent' && <Badge variant="info">AI</Badge>}
            </button>
          ))}
        </div>
      )}
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

function slugifyFolder(folder: string): string {
  if (!folder) return '';
  const normalized = folder
    .trim()
    .replace(/^\/+|\/+$/g, '')
    .split('/')
    .map((seg) => slugifySegment(seg))
    .filter(Boolean)
    .join('/');
  return normalized;
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      className={cn('shrink-0 transition-transform', open ? 'rotate-90' : 'rotate-0')}
    >
      <path
        d="M4.5 2.5L8 6 4.5 9.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" className="shrink-0">
      <path
        d="M3 7a2 2 0 012-2h5l2 2h9a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}
