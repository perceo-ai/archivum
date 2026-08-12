import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { FileText, Loader2 } from 'lucide-react';
import { search } from '../api';
import { useAppState } from '../store';
import type { SearchResult } from '../types';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './ui/Command';

interface QuickSearchModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function pageLabel(slug: string, title?: string | null) {
  return title?.trim() || slug;
}

export default function QuickSearchModal({ open, onOpenChange }: QuickSearchModalProps) {
  const { pages } = useAppState();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recentPages = useMemo(
    () =>
      [...pages]
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
        .slice(0, 8),
    [pages],
  );

  useEffect(() => {
    if (!open) {
      setQuery('');
      setResults([]);
      setError(null);
      setLoading(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    const timer = window.setTimeout(async () => {
      try {
        const nextResults = await search(trimmed);
        if (!cancelled) setResults(nextResults);
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message);
          setResults([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 180);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query]);

  function openPage(slug: string) {
    navigate(`/wiki/${slug}`);
    onOpenChange(false);
  }

  const hasQuery = query.trim().length > 0;

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <DialogPrimitive.Content className="soft-border fixed left-1/2 top-[12vh] z-50 w-[min(720px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-[8px] border bg-[#171616] shadow-2xl outline-none">
          <DialogPrimitive.Title className="sr-only">Search notes</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Search the vault and open a page.
          </DialogPrimitive.Description>
          <Command shouldFilter={!hasQuery} className="rounded-none bg-transparent">
            <CommandInput
              value={query}
              onValueChange={setQuery}
              placeholder="Search notes"
              autoFocus
              className="text-base"
            />
            <CommandList className="max-h-[56vh]">
              {loading && (
                <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Searching
                </div>
              )}
              {error && <div className="px-4 py-3 text-sm text-red-400">{error}</div>}
              {!loading && hasQuery && results.length === 0 && !error && (
                <CommandEmpty>No matching notes.</CommandEmpty>
              )}
              {hasQuery && results.length > 0 && (
                <CommandGroup heading="Results">
                  {results.map((result) => (
                    <CommandItem
                      key={result.slug}
                      value={`${result.title} ${result.slug}`}
                      onSelect={() => openPage(result.slug)}
                      className="items-start gap-3 rounded-[6px] px-3 py-3"
                    >
                      <FileText className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-foreground">{result.title}</div>
                        <div className="truncate text-xs text-muted-foreground">{result.slug}</div>
                        {result.excerpt ? (
                          <div className="mt-1 line-clamp-2 text-xs leading-5 text-text-secondary">
                            {result.excerpt}
                          </div>
                        ) : null}
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
              {!hasQuery && (
                <CommandGroup heading="Recent">
                  {recentPages.length === 0 ? (
                    <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                      No notes yet.
                    </div>
                  ) : (
                    recentPages.map((page) => (
                      <CommandItem
                        key={page.slug}
                        value={`${pageLabel(page.slug, page.title)} ${page.slug}`}
                        onSelect={() => openPage(page.slug)}
                        className="gap-3 rounded-[6px] px-3 py-3"
                      >
                        <FileText className="h-4 w-4 shrink-0 text-zinc-500" />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-foreground">
                            {pageLabel(page.slug, page.title)}
                          </div>
                          <div className="truncate text-xs text-muted-foreground">{page.slug}</div>
                        </div>
                      </CommandItem>
                    ))
                  )}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
