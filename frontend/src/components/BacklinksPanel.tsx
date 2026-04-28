import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b shrink-0" style={{ borderColor: '#3a3a4a' }}>
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          Linked from
        </span>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {loading && (
          <div className="px-3 py-2 space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="skeleton h-8 w-full" />
            ))}
          </div>
        )}

        {error && (
          <div className="px-3 py-3 text-xs text-red-400">{error}</div>
        )}

        {!loading && !error && backlinks.length === 0 && (
          <div className="px-3 py-6 text-center text-text-muted text-xs">
            {currentSlug ? 'No backlinks yet' : 'Open a page to see backlinks'}
          </div>
        )}

        {!loading && !error && backlinks.map((page) => (
          <button
            key={page.slug}
            onClick={() => navigate(`/wiki/${page.slug}`)}
            className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-white/5 hover:text-text-primary transition-colors group"
          >
            <div className="flex items-center gap-2">
              <BacklinkIcon />
              <span className="flex-1 truncate">{page.title}</span>
            </div>
            <p className="text-xs text-text-muted mt-0.5 pl-5 truncate">
              {page.slug}
            </p>
          </button>
        ))}
      </div>

      {currentSlug && (
        <div
          className="px-3 py-2 border-t shrink-0"
          style={{ borderColor: '#3a3a4a' }}
        >
          <p className="text-xs text-text-muted">
            {backlinks.length} {backlinks.length === 1 ? 'reference' : 'references'}
          </p>
        </div>
      )}
    </div>
  );
}

function BacklinkIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-text-muted shrink-0"
    >
      <path d="M7 1l4 4-4 4" />
      <path d="M1 9V7a5 5 0 015-5h5" />
    </svg>
  );
}
