import { useEffect, useState } from 'react';
import { createPage, previewCapture, type CapturePreview } from '../api';
import { useAppDispatch } from '../store';
import { useToast } from '../components/ui/Toast';

/**
 * The capture box at the top of the stream.
 *
 * Same contract as the ⌘C sheet: type anything, Archivum works out the filing
 * and shows its guess, and the guess never gates the save. The box is here
 * because capture should cost nothing — not even a keystroke to open it.
 */

function slugify(value: string): string {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .trim()
      .replace(/\s+/g, '-')
      .slice(0, 60) || 'untitled'
  );
}

function titleFrom(text: string): string {
  const firstLine = text.trim().split('\n')[0]?.trim() ?? '';
  if (!firstLine) return 'Untitled';
  return firstLine.length > 80 ? `${firstLine.slice(0, 77)}…` : firstLine;
}

export default function StreamComposer({ onCaptured }: { onCaptured: () => void }) {
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<CapturePreview | null>(null);
  const [saving, setSaving] = useState(false);
  const dispatch = useAppDispatch();
  const { push } = useToast();

  useEffect(() => {
    if (!text.trim()) {
      setPreview(null);
      return;
    }
    const id = window.setTimeout(() => {
      previewCapture(text)
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 250);
    return () => window.clearTimeout(id);
  }, [text]);

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
        tags: [preview?.kind ?? 'thought', ...(preview?.tags ?? [])],
        ...(folder ? { slug: `${folder}/${slugify(title)}` } : {}),
      });
      dispatch({ type: 'UPSERT_PAGE', page });
      setText('');
      setPreview(null);
      push({
        kind: 'success',
        title: 'Captured',
        description: folder ? `Filed into ${folder}` : 'Filed at the vault root',
      });
      onCaptured();
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

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          rows={1}
          value={text}
          placeholder="What happened, what you learned, what to remember…"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              void commit();
            }
          }}
        />

        {text.trim() && (
          <div className="comp-hint" style={{ display: 'flex' }}>
            {preview ? (
              <>
                <span>Will file as</span> <b>{preview.kind}</b>
                {preview.folder && (
                  <>
                    <span>into</span> <b>{preview.folder}</b>
                  </>
                )}
                {preview.links.length > 0 && (
                  <>
                    <span>·</span> <span>link to</span>{' '}
                    <b>{preview.links.map((link) => link.title).join(', ')}</b>
                  </>
                )}
              </>
            ) : (
              <span>Working out where this goes…</span>
            )}
          </div>
        )}

        <div className="comp-foot">
          <span style={{ fontSize: 'var(--t-12)', color: 'var(--text-3)', paddingLeft: 6 }}>
            {preview?.reason || 'Everything lands in the stream'}
          </span>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            style={{ marginLeft: 'auto' }}
            disabled={!text.trim() || saving}
            onClick={() => void commit()}
          >
            {saving ? 'Capturing…' : 'Capture'}
            <span
              className="kbd"
              style={{ background: 'rgba(255,255,255,.2)', borderColor: 'transparent', color: '#fff' }}
            >
              ⌘⏎
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
