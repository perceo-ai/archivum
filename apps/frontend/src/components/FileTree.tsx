import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppState, useAppDispatch } from '../store';
import {
  createFolder,
  createPage,
  deleteFolder,
  deletePage,
  duplicatePage,
  ingestFile,
  listFolders,
  listPages,
  moveFolder,
  movePage,
  renameFolder,
} from '../api';
import type { Folder } from '../types';
import { cn } from '../lib/cn';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { Badge } from './ui/Badge';
import { Dialog } from './ui/Dialog';
import { Popover, PopoverContent, PopoverTrigger } from './ui/Popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from './ui/Command';
import { ScrollArea } from './ui/ScrollArea';
import {
  Check,
  ChevronsUpDown,
  Copy,
  FilePlus2,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Trash2,
  Upload,
} from 'lucide-react';

type ActionKind =
  | 'new-page'
  | 'new-folder'
  | 'rename-page'
  | 'move-page'
  | 'duplicate-page'
  | 'rename-folder'
  | 'move-folder'
  | 'delete-page'
  | 'delete-folder';

type ActionState = {
  kind: ActionKind;
  page?: TreePage;
  folderPath?: string;
};

type ContextState =
  | { type: 'page'; page: TreePage; x: number; y: number }
  | { type: 'folder'; path: string; x: number; y: number };

export default function FileTree() {
  const { pages, currentSlug } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [filter, setFilter] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [action, setAction] = useState<ActionState | null>(null);
  const [draft, setDraft] = useState('');
  const [locationDraft, setLocationDraft] = useState('');
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [context, setContext] = useState<ContextState | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listFolders().then(setFolders).catch((err) => console.error('Failed to load folders:', err));
  }, []);

  useEffect(() => {
    if (!context) return;
    function close() {
      setContext(null);
    }
    document.addEventListener('click', close);
    window.addEventListener('blur', close);
    return () => {
      document.removeEventListener('click', close);
      window.removeEventListener('blur', close);
    };
  }, [context]);

  const sorted = [...pages].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );

  const normalizedFilter = filter.trim().toLowerCase();
  const filteredPages = normalizedFilter
    ? sorted.filter(
        (p) =>
          p.title.toLowerCase().includes(normalizedFilter) ||
          p.slug.toLowerCase().includes(normalizedFilter),
      )
    : sorted;
  const filteredFolders = normalizedFilter
    ? folders.filter((f) => f.path.toLowerCase().includes(normalizedFilter))
    : folders;

  const tree = useMemo(() => buildTree(filteredPages, filteredFolders), [filteredPages, filteredFolders]);
  const folderChoices = useMemo(() => folderOptions(tree), [tree]);
  const autoExpanded = useMemo(() => {
    if (!normalizedFilter) return null;
    const set = new Set<string>();
    for (const p of filteredPages) addAncestorFolders(set, p.slug);
    for (const f of filteredFolders) addAncestorFolders(set, `${f.path}/_`);
    return set;
  }, [normalizedFilter, filteredPages, filteredFolders]);

  async function refreshVault() {
    const [nextPages, nextFolders] = await Promise.all([listPages(), listFolders()]);
    dispatch({ type: 'SET_PAGES', pages: nextPages });
    setFolders(nextFolders);
  }

  function beginAction(next: ActionState, initialDraft = '', initialLocation = '') {
    setContext(null);
    setDraft(initialDraft);
    setLocationDraft(initialLocation);
    setFolderPickerOpen(false);
    setAction(next);
  }

  function closeAction() {
    setAction(null);
    setDraft('');
    setLocationDraft('');
    setFolderPickerOpen(false);
  }

  async function submitAction() {
    if (!action) return;
    try {
      if (action.kind === 'new-page') {
        if (!draft.trim()) return;
        const titleSlug = slugifySegment(draft) || 'untitled';
        const slug = locationDraft ? `${locationDraft}/${titleSlug}` : titleSlug;
        const page = await createPage({ slug, title: draft.trim(), content: `# ${draft.trim()}\n\n` });
        dispatch({ type: 'UPSERT_PAGE', page });
        navigate(`/wiki/${page.slug}`);
      }
      if (action.kind === 'new-folder') {
        const path = normalizeFolderPath(locationDraft ? `${locationDraft}/${draft}` : draft);
        if (!path) return;
        const folder = await createFolder({ path });
        setFolders((prev) => mergeFolder(prev, folder));
        setExpanded((prev) => new Set(prev).add(folder.path));
      }
      if (action.kind === 'rename-page' && action.page) {
        const name = slugifySegment(draft) || action.page.slug.split('/').pop()!;
        const nextSlug = replaceLeaf(action.page.slug, name);
        const page = await movePage(action.page.slug, { new_slug: nextSlug });
        dispatch({ type: 'DELETE_PAGE', slug: action.page.slug });
        dispatch({ type: 'UPSERT_PAGE', page });
        if (currentSlug === action.page.slug) navigate(`/wiki/${page.slug}`);
      }
      if (action.kind === 'move-page' && action.page) {
        const nextFolder = normalizeFolderPath(locationDraft);
        const leaf = action.page.slug.split('/').pop()!;
        const nextSlug = nextFolder ? `${nextFolder}/${leaf}` : leaf;
        const page = await movePage(action.page.slug, { new_slug: nextSlug });
        dispatch({ type: 'DELETE_PAGE', slug: action.page.slug });
        dispatch({ type: 'UPSERT_PAGE', page });
        if (currentSlug === action.page.slug) navigate(`/wiki/${page.slug}`);
      }
      if (action.kind === 'duplicate-page' && action.page) {
        const title = draft.trim() || `${action.page.title} copy`;
        const folder = normalizeFolderPath(locationDraft);
        const slug = `${folder ? `${folder}/` : ''}${slugifySegment(title) || `${action.page.slug}-copy`}`;
        const page = await duplicatePage(action.page.slug, { new_slug: slug, title });
        dispatch({ type: 'UPSERT_PAGE', page });
        navigate(`/wiki/${page.slug}`);
      }
      if (action.kind === 'rename-folder' && action.folderPath) {
        await renameFolder(action.folderPath, { name: slugifySegment(draft), recursive: true });
        await refreshVault();
      }
      if (action.kind === 'move-folder' && action.folderPath) {
        const nextPath = normalizeFolderPath(locationDraft);
        if (!nextPath) return;
        await moveFolder(action.folderPath, { new_path: nextPath, recursive: true });
        await refreshVault();
      }
      if (action.kind === 'delete-page' && action.page) {
        await deletePage(action.page.slug);
        dispatch({ type: 'DELETE_PAGE', slug: action.page.slug });
        if (currentSlug === action.page.slug) navigate('/ingest');
      }
      if (action.kind === 'delete-folder' && action.folderPath) {
        await deleteFolder(action.folderPath, { recursive: true });
        await refreshVault();
      }
      closeAction();
    } catch (err) {
      console.error('Vault action failed:', err);
    }
  }

  async function handleFileDrop(files: FileList) {
    for (const file of Array.from(files)) {
      try {
        await ingestFile(file);
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

  async function dropIntoFolder(targetPath: string, e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    const raw = e.dataTransfer.getData('text/plain');
    try {
      if (raw.startsWith('page:')) {
        const slug = raw.slice(5);
        const leaf = slug.split('/').pop()!;
        const nextSlug = targetPath ? `${targetPath}/${leaf}` : leaf;
        if (nextSlug !== slug) {
          const page = await movePage(slug, { new_slug: nextSlug });
          dispatch({ type: 'DELETE_PAGE', slug });
          dispatch({ type: 'UPSERT_PAGE', page });
          if (currentSlug === slug) navigate(`/wiki/${page.slug}`);
        }
      }
      if (raw.startsWith('folder:')) {
        const path = raw.slice(7);
        const leaf = path.split('/').pop()!;
        const nextPath = targetPath ? `${targetPath}/${leaf}` : leaf;
        if (nextPath !== path && !nextPath.startsWith(`${path}/`)) {
          await moveFolder(path, { new_path: nextPath, recursive: true });
          await refreshVault();
        }
      }
    } catch (err) {
      console.error('Move failed:', err);
    }
  }

  const isEmpty = filteredPages.length === 0 && filteredFolders.length === 0;

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
      <div className="subtle-divider shrink-0 border-b px-4 py-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Vault
          </span>
          <div className="flex items-center gap-1">
            <Button
              onClick={() => beginAction({ kind: 'new-folder' })}
              variant="ghost"
              size="icon"
              title="New folder"
              aria-label="New folder"
            >
              <FolderPlus className="h-4 w-4" />
            </Button>
            <Button
              onClick={() => beginAction({ kind: 'new-page' }, '', INBOX_FOLDER)}
              variant="ghost"
              size="icon"
              title="New page"
              aria-label="New page"
            >
              <FilePlus2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <Input
          type="text"
          placeholder="Filter vault..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          aria-label="Filter vault"
          className="h-10 text-sm"
        />
      </div>

      <ScrollArea className="flex-1 py-1">
        <div className="pb-2" onDragOver={(e) => e.preventDefault()} onDrop={(e) => dropIntoFolder('', e)}>
          {isEmpty && (
            <div className="px-3 py-4 text-center text-muted-foreground text-xs leading-5">
              {filter ? 'No matches' : 'No pages yet. Use Import files or the new-page button to start.'}
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
            onContext={setContext}
            onBeginAction={beginAction}
            onDropIntoFolder={dropIntoFolder}
          />
        </div>
      </ScrollArea>

      <div className="subtle-divider shrink-0 border-t px-4 py-4">
        <Button
          type="button"
          variant="secondary"
          size="default"
          className={cn(
            'w-full justify-center',
            'data-[dragover=true]:border-ring data-[dragover=true]:bg-accent/40',
          )}
          data-dragover={dragOver ? 'true' : 'false'}
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload className="h-4 w-4" />
          Import files...
        </Button>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => e.target.files && handleFileDrop(e.target.files)}
      />

      {context && (
        <ContextMenu
          context={context}
          onBeginAction={beginAction}
          onNavigate={(slug) => navigate(`/wiki/${slug}`)}
          onClose={() => setContext(null)}
          onToggle={(path) =>
            setExpanded((prev) => {
              const next = new Set(prev);
              if (next.has(path)) next.delete(path);
              else next.add(path);
              return next;
            })
          }
        />
      )}

      <ActionDialog
        action={action}
        draft={draft}
        locationDraft={locationDraft}
        folderChoices={folderChoices}
        folderPickerOpen={folderPickerOpen}
        onFolderPickerOpen={setFolderPickerOpen}
        onDraft={setDraft}
        onLocationDraft={setLocationDraft}
        onClose={closeAction}
        onSubmit={submitAction}
      />
    </div>
  );
}

export type TreePage = {
  slug: string;
  title: string;
  authored_by: 'user' | 'agent';
};

export type TreeNode = {
  name: string;
  path: string;
  explicit: boolean;
  folders: TreeNode[];
  pages: TreePage[];
};

export const DEFAULT_FOLDER_PATHS = [
  'inbox',
  'notes',
  'sources',
  'daily',
  'projects',
  'areas',
  'people',
  'archive',
] as const;

const DEFAULT_FOLDER_ORDER = new Map<string, number>(
  DEFAULT_FOLDER_PATHS.map((path, index) => [path, index]),
);
const INBOX_FOLDER = 'inbox';

export function buildTree(pages: TreePage[], folders: Folder[]): TreeNode {
  const root: TreeNode = { name: '', path: '', explicit: true, folders: [], pages: [] };
  const folderIndex = new Map<string, TreeNode>();
  folderIndex.set('', root);

  function ensureFolder(path: string, explicit = false): TreeNode {
    const existing = folderIndex.get(path);
    if (existing) {
      existing.explicit = existing.explicit || explicit;
      return existing;
    }
    const parts = path.split('/');
    const parentPath = parts.slice(0, -1).join('/');
    const name = parts[parts.length - 1]!;
    const parent = ensureFolder(parentPath);
    const node: TreeNode = { name, path, explicit, folders: [], pages: [] };
    parent.folders.push(node);
    folderIndex.set(path, node);
    return node;
  }

  for (const path of DEFAULT_FOLDER_PATHS) ensureFolder(path, true);
  for (const folder of folders) ensureFolder(folder.path, true);
  for (const p of pages) {
    const parts = p.slug.split('/');
    const folderPath = parts.slice(0, -1).join('/');
    const folder = folderPath ? ensureFolder(folderPath) : ensureFolder(INBOX_FOLDER, true);
    folder.pages.push({ slug: p.slug, title: p.title, authored_by: p.authored_by });
  }

  function sortNode(node: TreeNode) {
    node.folders.sort((a, b) => {
      const rankA = DEFAULT_FOLDER_ORDER.get(a.path) ?? Number.MAX_SAFE_INTEGER;
      const rankB = DEFAULT_FOLDER_ORDER.get(b.path) ?? Number.MAX_SAFE_INTEGER;
      if (rankA !== rankB) return rankA - rankB;
      return a.name.localeCompare(b.name);
    });
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
  onContext,
  onBeginAction,
  onDropIntoFolder,
}: {
  node: TreeNode;
  depth: number;
  currentSlug: string | null;
  onToggle: (path: string) => void;
  isExpanded: (path: string) => boolean;
  onNavigate: (slug: string) => void;
  onContext: (context: ContextState) => void;
  onBeginAction: (action: ActionState, draft?: string, location?: string) => void;
  onDropIntoFolder: (path: string, event: React.DragEvent) => void;
}) {
  const isRoot = node.path === '';
  const expanded = isRoot ? true : isExpanded(node.path);
  const hasChildren = node.folders.length > 0 || node.pages.length > 0;

  return (
    <div>
      {!isRoot && (
        <div
          className={cn(
            'group flex w-full items-center gap-1.5 px-2 py-2 text-sm text-muted-foreground transition-colors',
            'hover:bg-accent/50 hover:text-foreground',
          )}
          style={{ paddingLeft: 8 + depth * 12 }}
          draggable
          onDragStart={(e) => e.dataTransfer.setData('text/plain', `folder:${node.path}`)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => onDropIntoFolder(node.path, e)}
          onContextMenu={(e) => {
            e.preventDefault();
            onContext({ type: 'folder', path: node.path, x: e.clientX, y: e.clientY });
          }}
        >
          <button
            className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
            onClick={() => onToggle(node.path)}
          >
            <ChevronIcon open={expanded} />
            <FolderIcon />
            <span className="truncate">{node.name}</span>
            {!hasChildren && <span className="ml-2 text-[11px] text-muted-foreground/70">-</span>}
          </button>

          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
            aria-label="Folder actions"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              const rect = e.currentTarget.getBoundingClientRect();
              onContext({ type: 'folder', path: node.path, x: rect.right, y: rect.bottom });
            }}
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
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
              onContext={onContext}
              onBeginAction={onBeginAction}
              onDropIntoFolder={onDropIntoFolder}
            />
          ))}

          {node.pages.map((p) => (
            <button
              key={p.slug}
              draggable
              onDragStart={(e) => e.dataTransfer.setData('text/plain', `page:${p.slug}`)}
              onClick={() => onNavigate(p.slug)}
              onContextMenu={(e) => {
                e.preventDefault();
                onContext({ type: 'page', page: p, x: e.clientX, y: e.clientY });
              }}
              className={cn(
                'flex w-full items-start gap-2 rounded-xl px-2 py-2 text-left text-sm transition-colors',
                currentSlug === p.slug
                  ? 'bg-accent text-accent-foreground shadow-sm'
                  : 'text-muted-foreground hover:bg-accent/40 hover:text-foreground',
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

function ContextMenu({
  context,
  onBeginAction,
  onNavigate,
  onClose,
  onToggle,
}: {
  context: ContextState;
  onBeginAction: (action: ActionState, draft?: string, location?: string) => void;
  onNavigate: (slug: string) => void;
  onClose: () => void;
  onToggle: (path: string) => void;
}) {
  const items =
    context.type === 'page'
      ? [
          { label: 'Open', action: () => onNavigate(context.page.slug) },
          { label: 'Rename', icon: Pencil, action: () => onBeginAction({ kind: 'rename-page', page: context.page }, leafName(context.page.slug)) },
          { label: 'Move', action: () => onBeginAction({ kind: 'move-page', page: context.page }, '', parentPath(context.page.slug)) },
          { label: 'Duplicate', action: () => onBeginAction({ kind: 'duplicate-page', page: context.page }, `${context.page.title} copy`, parentPath(context.page.slug)) },
          { label: 'Copy path', icon: Copy, action: () => void navigator.clipboard?.writeText(context.page.slug) },
          { label: 'Delete', icon: Trash2, danger: true, action: () => onBeginAction({ kind: 'delete-page', page: context.page }) },
        ]
      : [
          { label: 'New page', icon: FilePlus2, action: () => onBeginAction({ kind: 'new-page', folderPath: context.path }, '', context.path) },
          { label: 'New folder', icon: FolderPlus, action: () => onBeginAction({ kind: 'new-folder', folderPath: context.path }, '', context.path) },
          { label: 'Rename', icon: Pencil, action: () => onBeginAction({ kind: 'rename-folder', folderPath: context.path }, leafName(context.path)) },
          { label: 'Move', action: () => onBeginAction({ kind: 'move-folder', folderPath: context.path }, '', context.path) },
          { label: 'Copy path', icon: Copy, action: () => void navigator.clipboard?.writeText(context.path) },
          { label: 'Expand/collapse', action: () => onToggle(context.path) },
          { label: 'Delete', icon: Trash2, danger: true, action: () => onBeginAction({ kind: 'delete-folder', folderPath: context.path }) },
        ];

  return (
    <div
      className="soft-border fixed z-50 min-w-44 rounded-md border bg-popover p-1 text-popover-foreground shadow-lg"
      style={{ left: context.x, top: context.y }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <button
            key={item.label}
            className={cn(
              'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent',
              item.danger && 'text-destructive',
            )}
            onClick={() => {
              item.action();
              onClose();
            }}
          >
            {Icon ? <Icon className="h-4 w-4" /> : <span className="h-4 w-4" />}
            <span>{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function ActionDialog({
  action,
  draft,
  locationDraft,
  folderChoices,
  folderPickerOpen,
  onFolderPickerOpen,
  onDraft,
  onLocationDraft,
  onClose,
  onSubmit,
}: {
  action: ActionState | null;
  draft: string;
  locationDraft: string;
  folderChoices: string[];
  folderPickerOpen: boolean;
  onFolderPickerOpen: (open: boolean) => void;
  onDraft: (value: string) => void;
  onLocationDraft: (value: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  const textLabel =
    action?.kind === 'rename-page' || action?.kind === 'rename-folder'
      ? 'Name'
      : action?.kind === 'delete-page' || action?.kind === 'delete-folder'
        ? ''
        : action?.kind === 'move-page' || action?.kind === 'move-folder'
          ? ''
          : 'Title';
  const needsLocation =
    action?.kind === 'new-page' ||
    action?.kind === 'new-folder' ||
    action?.kind === 'move-page' ||
    action?.kind === 'move-folder' ||
    action?.kind === 'duplicate-page';
  const needsText =
    action &&
    !['delete-page', 'delete-folder', 'move-page', 'move-folder'].includes(action.kind);
  const isDelete = action?.kind === 'delete-page' || action?.kind === 'delete-folder';

  return (
    <Dialog
      open={!!action}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={dialogTitle(action)}
      description={dialogDescription(action)}
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant={isDelete ? 'danger' : 'default'} onClick={onSubmit}>
            {isDelete ? 'Delete' : 'Apply'}
          </Button>
        </div>
      }
    >
      {!isDelete && (
        <div className="space-y-3">
          {needsLocation && (
            <div className="space-y-2">
              <div className="text-sm font-medium">Location</div>
              <FolderPicker
                value={locationDraft}
                folders={folderChoices}
                open={folderPickerOpen}
                onOpen={onFolderPickerOpen}
                onChange={onLocationDraft}
              />
            </div>
          )}
          {needsText && (
            <div className="space-y-2">
              <div className="text-sm font-medium">{textLabel}</div>
              <Input
                value={draft}
                onChange={(e) => onDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onSubmit();
                }}
                autoFocus
              />
            </div>
          )}
        </div>
      )}
    </Dialog>
  );
}

function FolderPicker({
  value,
  folders,
  open,
  onOpen,
  onChange,
}: {
  value: string;
  folders: string[];
  open: boolean;
  onOpen: (open: boolean) => void;
  onChange: (value: string) => void;
}) {
  return (
    <Popover open={open} onOpenChange={onOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open} className="w-full justify-between">
          <span className="truncate">{value ? value : 'Root'}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="p-0" align="start">
        <Command>
          <CommandInput placeholder="Search folders..." />
          <CommandList>
            <CommandEmpty>No folders found.</CommandEmpty>
            <CommandGroup heading="Folders">
              {folders.map((path) => (
                <CommandItem
                  key={path || '__root__'}
                  value={path || 'Root'}
                  onSelect={() => {
                    onChange(path);
                    onOpen(false);
                  }}
                >
                  <Check className={cn('mr-2 h-4 w-4', value === path ? 'opacity-100' : 'opacity-0')} />
                  <span className="truncate">{path || 'Root'}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function dialogTitle(action: ActionState | null): string {
  if (!action) return '';
  const titles: Record<ActionKind, string> = {
    'new-page': 'New page',
    'new-folder': 'New folder',
    'rename-page': 'Rename page',
    'move-page': 'Move page',
    'duplicate-page': 'Duplicate page',
    'rename-folder': 'Rename folder',
    'move-folder': 'Move folder',
    'delete-page': 'Delete page?',
    'delete-folder': 'Delete folder?',
  };
  return titles[action.kind];
}

function dialogDescription(action: ActionState | null): string {
  if (action?.kind === 'delete-folder') return 'This recursively removes child folders and pages.';
  if (action?.kind === 'delete-page') return 'This removes the markdown file and all page indexes.';
  if (action?.kind === 'move-folder') return 'Child pages and folders move with it.';
  return '';
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

function addAncestorFolders(set: Set<string>, slug: string) {
  const parts = slug.split('/').slice(0, -1);
  let acc = '';
  for (const part of parts) {
    acc = acc ? `${acc}/${part}` : part;
    set.add(acc);
  }
}

function mergeFolder(folders: Folder[], folder: Folder): Folder[] {
  const rest = folders.filter((f) => f.path !== folder.path);
  return [...rest, folder].sort((a, b) => a.path.localeCompare(b.path));
}

function normalizeFolderPath(path: string): string {
  return path
    .replace(/^\/+|\/+$/g, '')
    .split('/')
    .map((part) => slugifySegment(part))
    .filter(Boolean)
    .join('/');
}

function slugifySegment(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function parentPath(path: string): string {
  return path.split('/').slice(0, -1).join('/');
}

function leafName(path: string): string {
  return path.split('/').pop() ?? path;
}

function replaceLeaf(path: string, leaf: string): string {
  const parent = parentPath(path);
  return parent ? `${parent}/${leaf}` : leaf;
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
