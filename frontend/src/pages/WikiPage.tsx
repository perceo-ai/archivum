import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAppDispatch } from '../store';
import { getPage } from '../api';
import type { Page } from '../types';
import Editor from '../components/Editor/Editor';

export default function WikiPage() {
  const { slug } = useParams();
  const dispatch = useAppDispatch();
  const [page, setPage] = useState<Page | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    dispatch({ type: 'SET_CURRENT_SLUG', slug });
    setLoading(true);
    setError(null);
    getPage(slug)
      .then((p) => {
        setPage(p);
        dispatch({ type: 'UPSERT_PAGE', page: p });
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [slug, dispatch]);

  if (!slug) return null;

  return (
    <div className="flex flex-col h-full">
      {/* Title bar */}
      <div
        className="shrink-0 border-b px-5 py-3"
        style={{ borderColor: '#3a3a4a', backgroundColor: '#252535' }}
      >
        <div className="text-sm font-semibold text-text-primary">
          {page?.title ?? (loading ? 'Loading…' : slug)}
        </div>
        {error && <div className="text-xs text-red-400 mt-1">{error}</div>}
      </div>

      {/* Editor */}
      <div className="flex-1 overflow-hidden">
        {loading && !page && (
          <div className="p-6 space-y-2">
            <div className="skeleton h-4 w-full" />
            <div className="skeleton h-4 w-5/6" />
            <div className="skeleton h-4 w-4/5" />
          </div>
        )}

        {page && (
          <Editor
            slug={page.slug}
            initialContent={page.content}
            onSave={(s) => dispatch({ type: 'SET_SAVE_STATUS', status: s })}
          />
        )}
      </div>
    </div>
  );
}

