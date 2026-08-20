import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getActivity,
  reviewSuggestion,
  type ActivityItem,
  type MemorySuggestion,
  type SuggestionReviewAction,
} from '../api';
import { useToast } from '../components/ui/Toast';
import { Icon } from '../shell/Icon';
import StreamComposer from './StreamComposer';
import ShareHolds from './ShareHolds';
import { cn } from '../lib/cn';

/**
 * The stream is home: everything that happened, newest first.
 *
 * Review happens here rather than in a separate queue — a pending item sits at
 * the moment it landed, with the decision on the card. An empty tail is an
 * empty inbox.
 */

function relativeTime(iso: string): string {
  if (!iso) return '';
  const then = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`);
  const seconds = Math.round((Date.now() - then.getTime()) / 1000);
  if (Number.isNaN(seconds)) return '';
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h`;
  return then.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function dayLabel(iso: string): string {
  if (!iso) return 'Undated';
  const date = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return 'Undated';
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(date, today)) return 'Today';
  if (same(date, yesterday)) return 'Yesterday';
  return date.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' });
}

const KIND_ICON: Record<ActivityItem['kind'], string> = {
  page_created: 'plus',
  page_edited: 'pencil',
  suggestion: 'bot',
  ingest: 'database',
  memory: 'layers',
};

function verbFor(item: ActivityItem): string {
  switch (item.kind) {
    case 'page_created':
      return item.actor === 'agent' ? 'An agent wrote' : 'You wrote';
    case 'page_edited':
      return item.actor === 'agent' ? 'An agent edited' : 'You edited';
    case 'suggestion':
      return item.needs_review
        ? 'An agent wants to change something'
        : 'An agent suggested';
    case 'ingest':
      return 'You brought in';
    case 'memory':
      return 'Archivum remembered';
    default:
      return '';
  }
}

export default function StreamSurface() {
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [pending, setPending] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const navigate = useNavigate();
  const { push } = useToast();

  const load = useCallback(async (before?: string) => {
    try {
      const feed = await getActivity({ limit: 40, ...(before ? { before } : {}) });
      setItems((prev) => (before ? [...prev, ...feed.items] : feed.items));
      setNextBefore(feed.next_before);
      setPending(feed.pending_review);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load your stream');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function review(item: ActivityItem, action: SuggestionReviewAction) {
    const suggestionId = item.payload.suggestion_id as string | undefined;
    if (!suggestionId) return;
    setBusyId(item.id);
    try {
      const result: MemorySuggestion = await reviewSuggestion(suggestionId, action);
      setItems((prev) =>
        prev.map((entry) =>
          entry.id === item.id
            ? {
                ...entry,
                needs_review: false,
                payload: { ...entry.payload, status: result.status },
              }
            : entry,
        ),
      );
      setPending((count) => Math.max(0, count - 1));
      push({
        kind: 'success',
        title: action === 'accept' ? 'Accepted' : action === 'reject' ? 'Rejected' : 'Updated',
        description: item.title,
      });
    } catch (err) {
      push({
        kind: 'error',
        title: "That didn't go through",
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    } finally {
      setBusyId(null);
    }
  }

  const grouped = useMemo(() => {
    const groups: { label: string; items: ActivityItem[] }[] = [];
    for (const item of items) {
      const label = dayLabel(item.at);
      const last = groups[groups.length - 1];
      if (last && last.label === label) last.items.push(item);
      else groups.push({ label, items: [item] });
    }
    return groups;
  }, [items]);

  if (loading) return <div className="surface-loading">Opening your vault…</div>;
  if (error) return <div className="surface-error">{error}</div>;

  return (
    <div className="surface on">
      <div className="col">
        <StreamComposer onCaptured={() => void load()} />

        <ShareHolds />

        {pending > 0 && (
          <div className="needs">
            <span className="ic">
              <Icon name="alert" />
            </span>
            <div>
              <b>
                {pending} thing{pending === 1 ? '' : 's'} want
                {pending === 1 ? 's' : ''} into your memory.
              </b>{' '}
              <span className="sub">Nothing enters without you.</span>
            </div>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              style={{ marginLeft: 'auto' }}
              onClick={() => navigate('/entries?needs_review=1')}
            >
              Review them
            </button>
          </div>
        )}

        {items.length === 0 && (
          <div className="stream-empty">
            <h3>Nothing has happened yet</h3>
            <p>
              Press <span className="kbd">C</span> to capture a thought, or drop a file in to get
              started. Everything you or your agents do shows up here.
            </p>
          </div>
        )}

        <div className="stream">
          {grouped.map((group) => (
            <div key={group.label}>
              <div className="daybar">{group.label}</div>
              {group.items.map((item) => (
                <article
                  key={item.id}
                  className={cn(
                    'item',
                    item.actor === 'agent' && 'agent',
                    item.needs_review && 'pending',
                  )}
                >
                  <div className="when">{relativeTime(item.at)}</div>
                  <div
                    className="card"
                    role={item.slug ? 'button' : undefined}
                    tabIndex={item.slug ? 0 : undefined}
                    onClick={() => item.slug && navigate(`/wiki/${item.slug}`)}
                    onKeyDown={(event) => {
                      if (item.slug && (event.key === 'Enter' || event.key === ' ')) {
                        event.preventDefault();
                        navigate(`/wiki/${item.slug}`);
                      }
                    }}
                  >
                    <div className="who">
                      <Icon name={KIND_ICON[item.kind]} size={13} />
                      <span className="k">{verbFor(item)}</span>
                      {item.needs_review && (
                        <span className="chip chip-warn" style={{ marginLeft: 'auto' }}>
                          needs you
                        </span>
                      )}
                    </div>
                    <h3>{item.title}</h3>
                    {item.summary && <p>{item.summary}</p>}

                    {item.kind === 'suggestion' && item.needs_review && (
                      <div className="acts">
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          disabled={busyId === item.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void review(item, 'accept');
                          }}
                        >
                          <Icon name="check" />
                          Accept
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline btn-sm"
                          disabled={busyId === item.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void review(item, 'reject');
                          }}
                        >
                          <Icon name="x" />
                          Reject
                        </button>
                        {item.slug && (
                          <button
                            type="button"
                            className="where"
                            onClick={(event) => {
                              event.stopPropagation();
                              navigate(`/wiki/${item.slug}`);
                            }}
                          >
                            <Icon name="folder" size={11} />
                            {item.slug}
                          </button>
                        )}
                      </div>
                    )}

                    {item.kind === 'ingest' && (
                      <div className="tags">
                        <span className="chip">{String(item.payload.source_type ?? 'file')}</span>
                        <span className="chip">
                          {String(item.payload.pages_touched ?? 0)} pages touched
                        </span>
                        {item.payload.status === 'error' && (
                          <span className="chip chip-bad">failed</span>
                        )}
                      </div>
                    )}

                    {item.kind === 'memory' && (
                      <div className="tags">
                        <span className="chip">{String(item.payload.layer ?? '')}</span>
                        <span
                          className={cn(
                            'chip',
                            item.payload.status === 'active' && 'chip-ok',
                            Boolean(item.payload.disputed) && 'chip-warn',
                          )}
                        >
                          {item.payload.disputed ? 'disputed' : String(item.payload.status ?? '')}
                        </span>
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
          ))}
        </div>

        {nextBefore && (
          <div className="load-more">
            <button type="button" className="btn btn-outline btn-sm" onClick={() => void load(nextBefore)}>
              Load earlier
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
