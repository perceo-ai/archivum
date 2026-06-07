import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import DOMPurify from 'dompurify';
import { getPublicPage, listPublicPages } from '../api';
import type { PublicPage, PublicPageSummary } from '../api';

function renderMarkdown(text: string): string {
  return text
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold text-text-primary mt-4 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold text-text-primary mt-5 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold text-text-primary mt-6 mb-2">$1</h1>')
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 rounded text-xs font-mono" style="background:#2a2a3a;color:#cba6f7">$1</code>')
    .replace(/```[\w]*\n([\s\S]*?)```/g, '<pre class="my-3 p-3 rounded overflow-x-auto text-xs font-mono" style="background:#2a2a3a;color:#cdd6f4"><code>$1</code></pre>')
    .replace(/^> (.+)$/gm, '<blockquote class="border-l-2 pl-3 my-2 text-text-secondary italic" style="border-color:#4B91F1">$1</blockquote>')
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc text-text-secondary">$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal text-text-secondary">$1</li>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-accent hover:underline" target="_blank" rel="noopener">$1</a>')
    .replace(/^---$/gm, '<hr class="my-4" style="border-color:#3a3a4a">')
    .replace(/\n\n/g, '</p><p class="mb-3 text-text-secondary leading-relaxed">');
}

export default function PublicWikiPage() {
  const params = useParams();
  const navigate = useNavigate();
  const slug = params['*'];
  const [pages, setPages] = useState<PublicPageSummary[]>([]);
  const [page, setPage] = useState<PublicPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listPublicPages()
      .then((rows) => {
        setPages(rows);
        if (!slug && rows.length > 0) {
          navigate(`/public/wiki/${rows[0].slug}`, { replace: true });
        }
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [navigate, slug]);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    setError(null);
    getPublicPage(slug)
      .then((p) => setPage(p))
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [slug]);

  const sanitizedHtml = useMemo(() => {
    if (!page?.content) return '';
    return DOMPurify.sanitize(
      `<p class="mb-3 text-text-secondary leading-relaxed">${renderMarkdown(page.content)}</p>`,
      { ALLOWED_ATTR: ['class', 'style', 'href', 'target', 'rel'] },
    );
  }, [page?.content]);

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      <header className="h-12 border-b border-border flex items-center px-4 bg-panel/40">
        <Link to="/public" className="font-semibold tracking-wide">
          Archivum
        </Link>
      </header>
      <div className="grid min-h-[calc(100vh-3rem)] md:grid-cols-[280px_1fr]">
        <aside className="border-r border-border bg-panel/30 p-3 overflow-y-auto">
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Public wiki
          </div>
          <div className="space-y-1">
            {pages.map((p) => (
              <Link
                key={p.slug}
                to={`/public/wiki/${p.slug}`}
                className={`block rounded-md px-2 py-1.5 text-sm hover:bg-surface ${
                  p.slug === slug ? 'bg-surface text-accent' : 'text-text-secondary'
                }`}
              >
                {p.title}
              </Link>
            ))}
          </div>
        </aside>
        <main className="p-6 overflow-y-auto">
          {loading && <div className="text-sm text-muted-foreground">Loading...</div>}
          {!loading && error && (
            <div className="rounded-lg p-3 border border-red-400/25 bg-red-500/10 text-sm text-red-300">
              {error}
            </div>
          )}
          {!loading && !error && page && (
            <article className="max-w-3xl">
              <h1 className="text-2xl font-bold mb-4">{page.title}</h1>
              <div
                className="prose-custom text-text-secondary leading-relaxed"
                dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
              />
            </article>
          )}
        </main>
      </div>
    </div>
  );
}
