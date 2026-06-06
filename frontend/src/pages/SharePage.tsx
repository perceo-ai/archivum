import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import DOMPurify from 'dompurify';
import { getShare } from '../api';
import type { SharePage as SharePageType } from '../api';

function renderMarkdown(text: string): string {
  return text
    // Headings
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold text-text-primary mt-4 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold text-text-primary mt-5 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold text-text-primary mt-6 mb-2">$1</h1>')
    // Bold + italic
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 rounded text-xs font-mono" style="background:#2a2a3a;color:#cba6f7">$1</code>')
    // Code blocks
    .replace(/```[\w]*\n([\s\S]*?)```/g, '<pre class="my-3 p-3 rounded overflow-x-auto text-xs font-mono" style="background:#2a2a3a;color:#cdd6f4"><code>$1</code></pre>')
    // Blockquotes
    .replace(/^> (.+)$/gm, '<blockquote class="border-l-2 pl-3 my-2 text-text-secondary italic" style="border-color:#4B91F1">$1</blockquote>')
    // Unordered lists
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc text-text-secondary">$1</li>')
    // Ordered lists
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal text-text-secondary">$1</li>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-accent hover:underline" target="_blank" rel="noopener">$1</a>')
    // Horizontal rule
    .replace(/^---$/gm, '<hr class="my-4" style="border-color:#3a3a4a">')
    // Paragraphs (double newline)
    .replace(/\n\n/g, '</p><p class="mb-3 text-text-secondary leading-relaxed">');
}

export default function SharePage() {
  const params = useParams();
  const token = params['token'] as string | undefined;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [share, setShare] = useState<SharePageType | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    setShare(null);

    getShare(token)
      .then((s) => setShare(s))
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [token]);

  const body = share?.type === 'query' ? share.answer : share?.content;
  const sanitizedHtml = useMemo(() => {
    if (!body) return '';
    // Re-wrap as a single HTML blob to keep styling consistent.
    const html = `<p class="mb-3 text-text-secondary leading-relaxed">${renderMarkdown(body)}</p>`;
    return DOMPurify.sanitize(html, {
      ALLOWED_ATTR: ['class', 'style', 'href', 'target', 'rel'],
    });
  }, [body]);

  return (
    <div className="min-h-screen bg-bg">
      <div className="max-w-3xl mx-auto px-4 py-10">
        {loading && (
          <div className="space-y-2">
            <div className="skeleton h-6 w-2/3" />
            <div className="skeleton h-4 w-full" />
            <div className="skeleton h-4 w-5/6" />
          </div>
        )}

        {!loading && error && (
          <div className="rounded-lg p-3 border border-red-400/25 bg-red-500/10 text-sm text-red-300">
            {error}
          </div>
        )}

        {!loading && share && (
          <article>
            <h1 className="text-2xl font-bold text-text-primary mb-4">
              {share.type === 'query' ? share.question : share.title ?? 'Untitled'}
            </h1>

            {share.tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-5">
                {share.tags.slice(0, 6).map((t) => (
                  <span key={t} className="px-2 py-1 text-xs rounded border border-border text-text-secondary">
                    {t}
                  </span>
                ))}
              </div>
            )}

            <div
              className="prose-custom text-text-secondary leading-relaxed"
              dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
            />

            {share.type === 'query' && share.citations.length > 0 && (
              <div className="mt-6 pt-4 border-t border-border">
                <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                  Sources
                </h2>
                <div className="space-y-1">
                  {share.citations.map((citation) => (
                    <a
                      key={citation.slug}
                      href={`/wiki/${citation.slug}`}
                      className="block text-sm text-accent hover:underline"
                    >
                      {citation.title}
                    </a>
                  ))}
                </div>
              </div>
            )}

            {share.expires_at && (
              <div className="mt-8 text-xs text-muted-foreground">
                This share link expires at {share.expires_at}.
              </div>
            )}
          </article>
        )}
      </div>
    </div>
  );
}
