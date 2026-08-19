import { useEffect, useRef, useState } from 'react';
import { createPage, previewCapture, type CapturePreview } from '../api';
import { useAppDispatch } from '../store';
import { useToast } from '../components/ui/Toast';
import { Icon } from '../shell/Icon';
import { cn } from '../lib/cn';

/**
 * Capture: one box, no required fields.
 *
 * Archivum guesses the kind, folder, links and tags and shows its guess, but
 * the guess is advisory in both directions — the preview request is debounced
 * and its failure is swallowed, so capture never waits on it.
 */

const KINDS: { key: CapturePreview['kind']; label: string }[] = [
  { key: 'thought', label: 'Thought' },
  { key: 'note', label: 'Note' },
  { key: 'decision', label: 'Decision' },
  { key: 'person', label: 'Person' },
  { key: 'source', label: 'Source' },
];

/** Mirrors the backend's slug rules: lowercase, hyphenated, no punctuation. */
function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 60) || 'untitled';
}

function titleFrom(text: string): string {
  const firstLine = text.trim().split('\n')[0]?.trim() ?? '';
  if (!firstLine) return 'Untitled';
  return firstLine.length > 80 ? `${firstLine.slice(0, 77)}…` : firstLine;
}

export default function CaptureSheet({
  open,
  onClose,
  onCaptured,
}: {
  open: boolean;
  onClose: () => void;
  onCaptured: (slug: string | null) => void;
}) {
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<CapturePreview | null>(null);
  const [kind, setKind] = useState<CapturePreview['kind']>('thought');
  const [kindTouched, setKindTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const dispatch = useAppDispatch();
  const { push } = useToast();

  useEffect(() => {
    if (!open) return;
    setText('');
    setPreview(null);
    setKind('thought');
    setKindTouched(false);
    const id = window.setTimeout(() => inputRef.current?.focus(), 10);
    return () => window.clearTimeout(id);
  }, [open]);

  useEffect(() => {
    if (!open || !text.trim()) {
      setPreview(null);
      return;
    }
    const id = window.setTimeout(() => {
      previewCapture(text)
        .then((next) => {
          setPreview(next);
          // Respect an explicit choice; only follow the guess until then.
          if (!kindTouched) setKind(next.kind);
        })
        .catch(() => setPreview(null));
    }, 250);
    return () => window.clearTimeout(id);
  }, [text, open, kindTouched]);

  async function commit() {
    const body = text.trim();
    if (!body || saving) return;
    setSaving(true);
    try {
      const folder = preview?.folder ?? '';
      const title = titleFrom(body);
      const page = await createPage({
        title,
        content: body,
        tags: [kind, ...(preview?.tags ?? [])],
        // Only steer the slug when we know which folder it belongs in; the
        // backend derives it from the title otherwise.
        ...(folder ? { slug: `${folder}/${slugify(title)}` } : {}),
      });
      dispatch({ type: 'UPSERT_PAGE', page });
      push({
        kind: 'success',
        title: 'Captured',
        description: folder ? `Filed into ${folder}` : 'Filed at the vault root',
      });
      onCaptured(page.slug);
    } catch (error) {
      push({
        kind: 'error',
        title: "Couldn't capture that",
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="overlay on"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="sheet" role="dialog" aria-label="Capture">
        <div className="sheet-in" style={{ alignItems: 'flex-start' }}>
          <Icon name="zap" size={18} />
          <textarea
            ref={inputRef}
            rows={4}
            value={text}
            placeholder="Anything. A thought, a link, a quote, a decision, who you talked to…"
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                void commit();
              }
            }}
          />
        </div>

        <div
          style={{
            padding: '12px 17px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            flexWrap: 'wrap',
            gap: 7,
            alignItems: 'center',
          }}
        >
          <span style={{ fontSize: 'var(--t-12)', color: 'var(--text-3)' }}>File as</span>
          {KINDS.map((option) => (
            <button
              key={option.key}
              type="button"
              className={cn('facet', kind === option.key && 'on')}
              onClick={() => {
                setKind(option.key);
                setKindTouched(true);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div
          style={{
            padding: '12px 17px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
          }}
        >
          {preview?.folder && (
            <span className="chip">
              <Icon name="folder" size={11} />
              {preview.folder}
            </span>
          )}
          {preview?.links.map((link) => (
            <span key={link.slug} className="chip chip-accent">
              → {link.title}
            </span>
          ))}
          {preview?.tags.map((tag) => (
            <span key={tag} className="chip">
              #{tag}
            </span>
          ))}
          <button
            type="button"
            className="btn btn-primary btn-sm"
            style={{ marginLeft: 'auto' }}
            disabled={!text.trim() || saving}
            onClick={() => void commit()}
          >
            {saving ? 'Capturing…' : 'Capture'}
            <span className="kbd" style={{ background: 'rgba(255,255,255,.2)', borderColor: 'transparent', color: '#fff' }}>
              ⌘⏎
            </span>
          </button>
        </div>

        <div className="sheet-foot">
          <span>{preview?.reason || 'Filing is worked out as you type'}</span>
          <a href="/ingest" style={{ textDecoration: 'underline' }}>
            Bring in a file or URL instead
          </a>
          <span style={{ marginLeft: 'auto' }}>you can move it later from the vault tree</span>
        </div>
      </div>
    </div>
  );
}
