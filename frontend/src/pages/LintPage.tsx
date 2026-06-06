import { useState, useEffect, useCallback } from 'react';
import { lintWiki, applyLintFix, type LintIssue } from '../api';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';

export default function LintPage() {
  const [issues, setIssues] = useState<LintIssue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fixing, setFixing] = useState<string | null>(null);
  const [messages, setMessages] = useState<Record<string, string>>({});

  const fetchLint = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await lintWiki();
      setIssues(data.issues);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load lint results');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLint();
  }, [fetchLint]);

  async function handleFix(issue: LintIssue) {
    const key = issueKey(issue);
    setFixing(key);
    setMessages((prev) => ({ ...prev, [key]: '' }));

    try {
      const payload: { type: string; [key: string]: string } = { type: issue.type };

      if (issue.type === 'broken_wikilink') {
        payload.source_slug = issue.page;
        payload.link_target = issue.target ?? '';
      } else if (issue.type === 'orphan' || issue.type === 'orphan_page') {
        payload.slug = issue.page;
        // Normalize type to what backend expects
        payload.type = 'orphan';
      }

      const result = await applyLintFix(payload);

      if (result.detail === 'no_auto_fix') {
        setMessages((prev) => ({ ...prev, [key]: result.message ?? 'No auto-fix available' }));
      } else if (result.detail === 'no_change') {
        setMessages((prev) => ({ ...prev, [key]: 'Link not found in page content' }));
      } else {
        // Success — refresh the list
        await fetchLint();
      }
    } catch (e) {
      setMessages((prev) => ({
        ...prev,
        [key]: e instanceof Error ? e.message : 'Fix failed',
      }));
    } finally {
      setFixing(null);
    }
  }

  function issueKey(issue: LintIssue) {
    return `${issue.type}::${issue.page}::${issue.target ?? ''}`;
  }

  const brokenLinks = issues.filter((i) => i.type === 'broken_wikilink');
  const orphans = issues.filter((i) => i.type === 'orphan_page');

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-3xl mx-auto w-full">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-text-primary">Lint</h1>
        <Button onClick={fetchLint} variant="outline" size="sm" disabled={loading}>
          {loading ? 'Checking...' : 'Refresh'}
        </Button>
      </div>

      {error && (
        <p className="text-sm text-destructive mb-4">{error}</p>
      )}

      {!loading && (
        <div className="flex gap-4 mb-6">
          <div className="rounded-lg border border-border bg-card px-4 py-3 flex flex-col">
            <span className="text-2xl font-semibold text-text-primary">{brokenLinks.length}</span>
            <span className="text-xs text-text-secondary">Broken wikilinks</span>
          </div>
          <div className="rounded-lg border border-border bg-card px-4 py-3 flex flex-col">
            <span className="text-2xl font-semibold text-text-primary">{orphans.length}</span>
            <span className="text-xs text-text-secondary">Orphan pages</span>
          </div>
        </div>
      )}

      {brokenLinks.length > 0 && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">Broken Wikilinks</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {brokenLinks.map((issue) => {
              const key = issueKey(issue);
              const isBusy = fixing === key;
              const msg = messages[key];
              return (
                <div key={key} className="flex items-start justify-between gap-3 py-2 border-b border-border last:border-0">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <code className="text-xs text-text-primary font-mono">{issue.page}</code>
                      <span className="text-xs text-text-secondary">references missing page</span>
                      <Badge variant="destructive" className="text-xs font-mono">{issue.target}</Badge>
                    </div>
                    {msg && (
                      <p className="text-xs text-text-secondary mt-1">{msg}</p>
                    )}
                  </div>
                  <Button
                    onClick={() => handleFix(issue)}
                    disabled={isBusy}
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                  >
                    {isBusy ? 'Fixing...' : 'Fix'}
                  </Button>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {orphans.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Orphan Pages</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {orphans.map((issue) => {
              const key = issueKey(issue);
              const msg = messages[key];
              return (
                <div key={key} className="flex items-start justify-between gap-3 py-2 border-b border-border last:border-0">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <code className="text-xs text-text-primary font-mono">{issue.page}</code>
                      <span className="text-xs text-text-secondary">has no inbound or outbound links</span>
                    </div>
                    {msg && (
                      <p className="text-xs text-text-secondary mt-1">{msg}</p>
                    )}
                  </div>
                  <div title="Delete page manually or add a wikilink">
                    <Button
                      onClick={() => handleFix(issue)}
                      variant="outline"
                      size="sm"
                      disabled
                      className="shrink-0 opacity-40 cursor-not-allowed"
                    >
                      Fix
                    </Button>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {!loading && issues.length === 0 && (
        <div className="text-center py-12 text-text-secondary text-sm">
          No issues found. Your wiki is clean.
        </div>
      )}
    </div>
  );
}
