import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Page } from '../types';
import { Icon } from './Icon';
import { cn } from '../lib/cn';

/**
 * The vault as it exists on disk.
 *
 * Built from page slugs rather than a separate folder listing, so the tree can
 * never disagree with the files. Folders that hold something awaiting review
 * carry an amber dot, which is how "needs you" stays findable while browsing.
 */

type TreeNode = {
  name: string;
  path: string;
  children: Map<string, TreeNode>;
  page?: Page;
};

function buildTree(pages: Page[]): TreeNode {
  const root: TreeNode = { name: '', path: '', children: new Map() };
  for (const page of pages) {
    const parts = page.slug.split('/');
    let node = root;
    parts.forEach((part, index) => {
      const path = parts.slice(0, index + 1).join('/');
      let child = node.children.get(part);
      if (!child) {
        child = { name: part, path, children: new Map() };
        node.children.set(part, child);
      }
      if (index === parts.length - 1) child.page = page;
      node = child;
    });
  }
  return root;
}

function sortedChildren(node: TreeNode): TreeNode[] {
  return [...node.children.values()].sort((a, b) => {
    const aDir = a.children.size > 0;
    const bDir = b.children.size > 0;
    if (aDir !== bDir) return aDir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

function hasWaiting(node: TreeNode, waiting: Set<string>): boolean {
  if (node.page && waiting.has(node.page.slug)) return true;
  for (const child of node.children.values()) {
    if (hasWaiting(child, waiting)) return true;
  }
  return false;
}

function Row({
  node,
  depth,
  open,
  currentSlug,
  waiting,
  onToggle,
}: {
  node: TreeNode;
  depth: number;
  open: Set<string>;
  currentSlug: string | null;
  waiting: Set<string>;
  onToggle: (path: string) => void;
}) {
  const navigate = useNavigate();
  const isDir = node.children.size > 0;
  const isOpen = open.has(node.path);
  const waits = hasWaiting(node, waiting);

  return (
    <>
      <button
        type="button"
        className={cn('trow', isDir && 'folder', node.page?.slug === currentSlug && 'on')}
        style={{ paddingLeft: 6 + depth * 12 }}
        onClick={() => {
          if (isDir) onToggle(node.path);
          else if (node.page) navigate(`/wiki/${node.page.slug}`);
        }}
        title={node.path}
      >
        <i className={cn('tw', !isDir && 'leaf', isDir && !isOpen && 'closed')} data-i="chevronDown">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </i>
        <Icon name={isDir ? 'folder' : 'file'} className="ic" />
        <span className="nm">{node.name}</span>
        {waits && <span className="wait" title="Something in here is waiting on you" />}
      </button>
      {isDir &&
        isOpen &&
        sortedChildren(node).map((child) => (
          <Row
            key={child.path}
            node={child}
            depth={depth + 1}
            open={open}
            currentSlug={currentSlug}
            waiting={waiting}
            onToggle={onToggle}
          />
        ))}
    </>
  );
}

export default function VaultTree({
  pages,
  currentSlug,
  waiting,
}: {
  pages: Page[];
  currentSlug: string | null;
  waiting: Set<string>;
}) {
  const tree = useMemo(() => buildTree(pages), [pages]);
  const [open, setOpen] = useState<Set<string>>(() => {
    // Reveal the folders leading to whatever is open, so the tree always shows
    // where you are without needing an explicit "reveal" step.
    const next = new Set<string>();
    if (currentSlug) {
      const parts = currentSlug.split('/');
      for (let i = 1; i < parts.length; i += 1) next.add(parts.slice(0, i).join('/'));
    }
    return next;
  });

  function toggle(path: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  const roots = sortedChildren(tree);
  if (roots.length === 0) {
    return <p className="sb-note">Nothing here yet. Capture something and it will land in the vault.</p>;
  }

  return (
    <div className="tree">
      {roots.map((node) => (
        <Row
          key={node.path}
          node={node}
          depth={0}
          open={open}
          currentSlug={currentSlug}
          waiting={waiting}
          onToggle={toggle}
        />
      ))}
    </div>
  );
}
