import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { search } from '../api';
import type { SearchResult } from '../types';
import { Button } from './ui/Button';
import { Card } from './ui/Card';
import { Input } from './ui/Input';

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
    <div className="flex flex-col h-full bg-bg">
      <div
        className="shrink-0 border-b border-border p-4 bg-panel/40 backdrop-blur supports-[backdrop-filter]:bg-panel/30"
      >
        <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
          Search
        </h2>
        <form onSubmit={runSearch} className="flex gap-2">
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search your knowledge base..."
          />
          <Button
            type="submit"
            variant="primary"
            disabled={loading || !q.trim()}
          >
            {loading ? 'Searching…' : 'Search'}
          </Button>
        </form>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {error && (
          <div className="rounded-lg p-3 mb-4 text-sm text-red-300 border border-red-400/25 bg-red-500/10">
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
          <div className="text-sm text-muted-foreground">No results.</div>
        )}

        <div className="space-y-3">
          {results.map((r) => (
            <button
              key={r.slug}
              onClick={() => navigate(`/wiki/${r.slug}`)}
              className="w-full text-left transition-colors"
            >
              <Card className="p-3 hover:border-accent/30">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm text-foreground font-medium truncate">{r.title}</div>
                    <div className="text-xs text-muted-foreground truncate">{r.slug}</div>
                  </div>
                  <div className="text-xs text-muted-foreground shrink-0">{r.score.toFixed(3)}</div>
                </div>
                <div className="mt-2 text-sm text-muted-foreground leading-relaxed">
                  {r.excerpt}
                </div>
              </Card>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

