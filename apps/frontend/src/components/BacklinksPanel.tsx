import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CornerDownRight } from 'lucide-react';
import { useAppState } from '../store';
import { getBacklinks } from '../api';
import type { Page } from '../types';

export default function BacklinksPanel() {
  const { currentSlug } = useAppState();
  const navigate = useNavigate();
  const [backlinks, setBacklinks] = useState<Page[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentSlug) {
      setBacklinks([]);
      return;
    }

    setLoading(true);
    setError(null);

    getBacklinks(currentSlug)
      .then((pages) => {
        setBacklinks(pages);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [currentSlug]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto py-1">
        {loading && (
          <div className="space-y-2 py-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="skeleton h-8 w-full" />
            ))}
          </div>
        )}

        {error && (
          <div className="py-3 text-xs text-destructive">{error}</div>
        )}

        {!loading && !error && backlinks.length === 0 && (
          <div className="px-1 py-2 text-xs leading-5 text-muted-foreground">
            {currentSlug ? 'No backlinks yet' : 'Open a page to see backlinks'}
          </div>
        )}

        {!loading && !error && backlinks.map((page) => (
          <button
            key={page.slug}
            onClick={() => navigate(`/wiki/${page.slug}`)}
            className="group w-full rounded-[5px] px-2 py-1.5 text-left text-sm text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
          >
            <div className="flex items-center gap-2">
              <CornerDownRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
              <span className="flex-1 truncate">{page.title}</span>
            </div>
            <p className="mt-0.5 truncate pl-5 text-xs text-muted-foreground/60">
              {page.slug}
            </p>
          </button>
        ))}
      </div>

      {currentSlug && (
        <div className="mt-2 px-1">
          <p className="text-xs text-muted-foreground/70">
            {backlinks.length} {backlinks.length === 1 ? 'reference' : 'references'}
          </p>
        </div>
      )}
    </div>
  );
}
