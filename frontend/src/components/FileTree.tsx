import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppState, useAppDispatch } from '../store';
import { createPage, ingestFile } from '../api';
import type { IngestProgress } from '../types';
import { cn } from '../lib/cn';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { Badge } from './ui/Badge';
import { Dialog } from './ui/Dialog';
import { Popover, PopoverContent, PopoverTrigger } from './ui/Popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from './ui/Command';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/DropdownMenu';
import { ScrollArea } from './ui/ScrollArea';
import { Check, ChevronsUpDown, FilePlus2, MoreHorizontal, Upload } from 'lucide-react';

export default function FileTree() {
  const { pages, currentSlug } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [filter, setFilter] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createTitle, setCreateTitle] = useState('');
  const [createFolder, setCreateFolder] = useState<string>('');
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
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
    if (!createTitle.trim()) return;
    const titleSlug = slugifySegment(createTitle.trim()) || 'untitled';
    const folderSlug = createFolder;
    const slug = folderSlug ? `${folderSlug}/${titleSlug}` : titleSlug;
    try {
      const page = await createPage({
        slug,
        title: createTitle.trim(),
        content: `# ${createTitle.trim()}\n\n`,
      });
      dispatch({ type: 'UPSERT_PAGE', page });
      setCreateOpen(false);
      setCreateTitle('');
      setCreateFolder('');
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
      className={cn(
        'flex flex-col h-full',
        dragOver && 'outline-dashed outline-2 outline-ring outline-offset-[-2px]',
      )}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      data-dragover={dragOver ? 'true' : 'false'}
    >
      {/* Header */}
      <div className="px-3 py-2 border-b border-border shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Pages
          </span>
          <Button
            onClick={() => {
              setCreateFolder('');
              setCreateOpen(true);
            }}
            variant="ghost"
            size="icon"
            title="New page"
            aria-label="New page"
          >
            <FilePlus2 className="h-4 w-4" />
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

      {/* Pages list */}
      <ScrollArea className="flex-1 py-1">
        <div className="pb-2">
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
            onNewPageInFolder={(folderPath) => {
              setCreateFolder(folderPath);
              setCreateOpen(true);
            }}
          />
        </div>
      </ScrollArea>

      {/* Drop hint */}
      <div className="px-3 py-2 border-t border-border shrink-0">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn(
            'w-full justify-center',
            'data-[dragover=true]:border-ring data-[dragover=true]:bg-accent/40',
          )}
          data-dragover={dragOver ? 'true' : 'false'}
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload className="h-4 w-4" />
          Import files…
        </Button>
        <div className="mt-2 text-[11px] text-muted-foreground text-center">
          You can also drag & drop files anywhere in this sidebar.
        </div>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => e.target.files && handleFileDrop(e.target.files)}
      />

      <Dialog
        open={createOpen}
        onOpenChange={(o) => {
          setCreateOpen(o);
          if (!o) {
            setFolderPickerOpen(false);
            setCreateTitle('');
            setCreateFolder('');
          }
        }}
        title="New page"
        description="Choose where it lives, then type a title."
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button variant="default" onClick={handleCreatePage} disabled={!createTitle.trim()}>
              Create
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          <div className="space-y-2">
            <div className="text-sm font-medium">Location</div>
            <Popover open={folderPickerOpen} onOpenChange={setFolderPickerOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={folderPickerOpen}
                  className="w-full justify-between"
                >
                  <span className="truncate">
                    {createFolder ? createFolder : 'Root'}
                  </span>
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search folders..." />
                  <CommandList>
                    <CommandEmpty>No folders found.</CommandEmpty>
                    <CommandGroup heading="Folders">
                      {folderOptions(tree).map((path) => (
                        <CommandItem
                          key={path || '__root__'}
                          value={path || 'Root'}
                          onSelect={() => {
                            setCreateFolder(path);
                            setFolderPickerOpen(false);
                          }}
                        >
                          <Check
                            className={cn(
                              'mr-2 h-4 w-4',
                              createFolder === path ? 'opacity-100' : 'opacity-0',
                            )}
                          />
                          <span className="truncate">{path || 'Root'}</span>
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>

          <div className="space-y-2">
            <div className="text-sm font-medium">Title</div>
            <Input
              value={createTitle}
              onChange={(e) => setCreateTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreatePage();
              }}
              placeholder="e.g. Meeting notes"
              autoFocus
            />
          </div>
        </div>
      </Dialog>
    </div>
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

function folderOptions(tree: TreeNode): string[] {
  const out: string[] = [''];
  function walk(node: TreeNode) {
    for (const f of node.folders) {
      out.push(f.path);
      walk(f);
    }
  }
  walk(tree);
  return out;
}

function TreeFolder({
  node,
  depth,
  currentSlug,
  onToggle,
  isExpanded,
  onNavigate,
  onNewPageInFolder,
}: {
  node: TreeNode;
  depth: number;
  currentSlug: string | null;
  onToggle: (path: string) => void;
  isExpanded: (path: string) => boolean;
  onNavigate: (slug: string) => void;
  onNewPageInFolder: (folderPath: string) => void;
}) {
  const isRoot = node.path === '';
  const expanded = isRoot ? true : isExpanded(node.path);
  const hasChildren = node.folders.length > 0 || node.pages.length > 0;

  return (
    <div>
      {!isRoot && (
        <div
          className={cn(
            'w-full px-2 py-1.5 text-xs transition-colors flex items-center gap-1.5 group',
            'hover:bg-muted/50 text-muted-foreground hover:text-foreground',
          )}
          style={{ paddingLeft: 8 + depth * 12 }}
        >
          <button
            className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
            onClick={() => onToggle(node.path)}
          >
            <ChevronIcon open={expanded} />
            <FolderIcon />
            <span className="truncate">{node.name}</span>
            {!hasChildren && <span className="ml-2 text-[11px] text-muted-foreground/70">—</span>}
          </button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 opacity-0 group-hover:opacity-100"
                aria-label="Folder actions"
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onSelect={() => onNewPageInFolder(node.path)}
                className="gap-2"
              >
                <FilePlus2 className="h-4 w-4" />
                New page here
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  void navigator.clipboard?.writeText(node.path);
                }}
              >
                Copy folder path
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => onToggle(node.path)}
                className="gap-2"
              >
                {expanded ? (
                  <>
                    <ChevronsUpDown className="h-4 w-4 rotate-180" />
                    Collapse
                  </>
                ) : (
                  <>
                    <ChevronsUpDown className="h-4 w-4" />
                    Expand
                  </>
                )}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
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
              onNewPageInFolder={onNewPageInFolder}
            />
          ))}

          {node.pages.map((p) => (
            <button
              key={p.slug}
              onClick={() => onNavigate(p.slug)}
              className={cn(
                'w-full text-left px-2 py-2 text-sm transition-colors flex items-start gap-2',
                currentSlug === p.slug
                  ? 'bg-accent/10 text-foreground'
                  : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
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
