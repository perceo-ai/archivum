import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { search } from '../api';
import type { SearchResult } from '../types';

export default function SearchBar() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await search(q.trim());
      setResults(res);
    } catch (err) {
      setError((err as Error).message);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: '#1e1e2e' }}>
      <div
        className="shrink-0 border-b p-4"
        style={{ borderColor: '#3a3a4a', backgroundColor: '#252535' }}
      >
        <h2 className="text-sm font-semibold text-text-secondary mb-3 uppercase tracking-wider">
          Search
        </h2>
        <form onSubmit={runSearch} className="flex gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search your knowledge base..."
            className="flex-1 bg-transparent border rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/50"
            style={{ borderColor: '#3a3a4a' }}
          />
          <button
            type="submit"
            disabled={loading || !q.trim()}
            className="px-4 py-2 rounded text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ backgroundColor: '#4B91F1', color: '#ffffff' }}
          >
            {loading ? 'Searching…' : 'Search'}
          </button>
        </form>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {error && (
          <div
            className="rounded p-3 mb-4 text-sm text-red-400 border border-red-400/30"
            style={{ backgroundColor: '#2a1a1a' }}
          >
            {error}
          </div>
        )}

        {loading && (
          <div className="space-y-2">
            <div className="skeleton h-4 w-full" />
            <div className="skeleton h-4 w-5/6" />
            <div className="skeleton h-4 w-4/5" />
          </div>
        )}

        {!loading && !error && results.length === 0 && q.trim() && (
          <div className="text-sm text-text-muted">No results.</div>
        )}

        <div className="space-y-3">
          {results.map((r) => (
            <button
              key={r.slug}
              onClick={() => navigate(`/wiki/${r.slug}`)}
              className="w-full text-left rounded border p-3 hover:border-accent/40 transition-colors"
              style={{ borderColor: '#3a3a4a', backgroundColor: '#252535' }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm text-text-primary font-medium truncate">{r.title}</div>
                  <div className="text-xs text-text-muted truncate">{r.slug}</div>
                </div>
                <div className="text-xs text-text-muted shrink-0">{r.score.toFixed(3)}</div>
              </div>
              <div className="mt-2 text-sm text-text-secondary leading-relaxed">
                {r.excerpt}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

