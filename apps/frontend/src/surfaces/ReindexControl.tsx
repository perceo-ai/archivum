import { useState } from 'react';
import { reindexPage, type ReindexResult } from '../api';
import { useToast } from '../components/ui/Toast';
import { Icon } from '../shell/Icon';

/**
 * Tell Archivum to re-read this page from disk.
 *
 * The vault is markdown you own, so you might have edited this file in
 * Obsidian, in vim, or by pulling a branch. The watcher usually notices, but
 * "usually" is not something you can see, and a store you can't verify is one
 * you stop trusting. This is the visible counterpart: press it, and the file
 * on disk becomes the truth again.
 *
 * Degraded results are reported rather than swallowed. If the embedding or the
 * graph projection didn't land, the page is still saved — but you should know
 * that search won't find it yet, because the alternative is silently believing
 * the vault is more indexed than it is.
 */
export default function ReindexControl({ slug }: { slug: string }) {
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<ReindexResult | null>(null);
  const { push } = useToast();

  async function run() {
    setBusy(true);
    try {
      const result = await reindexPage(slug);
      setLast(result);
      if (result.degraded.length > 0) {
        push({
          kind: 'error',
          title: 'Indexed, with gaps',
          description: `${describeDegraded(result.degraded)} didn't update. The page is saved; try again in a moment.`,
        });
      } else {
        push({
          kind: 'success',
          title: result.action === 'unchanged' ? 'Already up to date' : 'Reindexed from disk',
          description: slug,
        });
      }
    } catch (error) {
      push({
        kind: 'error',
        title: "Couldn't reindex",
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="reindex">
      <button
        type="button"
        className="btn btn-icon btn-sm"
        title="Re-read this page from disk"
        aria-label="Re-read this page from disk"
        disabled={busy}
        onClick={run}
      >
        <Icon name="history" className={busy ? 'spin' : undefined} />
      </button>
      {last && last.degraded.length > 0 && (
        // Amber, because nobody has decided what to do about it yet.
        <span className="degraded" title={last.degraded.join(', ')}>
          <Icon name="alert" />
          {describeDegraded(last.degraded)} out of date
        </span>
      )}
    </div>
  );
}

/**
 * Name the projections the way someone using Archivum would think of them.
 *
 * The backend reports graph.node, graph.edges and graph.knowledge separately,
 * which describes the implementation rather than the consequence — that the
 * graph is stale. Only the first name is capitalised, so the result reads as
 * one phrase wherever it lands.
 */
export function describeDegraded(degraded: string[]): string {
  const names = [...new Set(
    degraded.map((item) => (item === 'search' ? 'search' : 'the graph')),
  )];
  const phrase = names.join(' and ');
  return phrase.charAt(0).toUpperCase() + phrase.slice(1);
}
