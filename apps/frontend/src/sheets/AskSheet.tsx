import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { query } from '../api';
import type { Page } from '../types';
import { Icon } from '../shell/Icon';
import { cn } from '../lib/cn';

/**
 * One sheet, two modes.
 *
 * `file` (⌘P) jumps to a page by path. `ask` (⌘K) answers from the vault with
 * citations. They share a surface because they answer the same impulse — "get
 * me to the thing" — and separating them into two overlays would double the
 * chrome for no gain.
 */

type Mode = 'ask' | 'file';

export default function AskSheet({
  open,
  mode,
  onModeChange,
  onClose,
  pages,
}: {
  open: boolean;
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  onClose: () => void;
  pages: Page[];
}) {
  const [text, setText] = useState('');
  const [cursor, setCursor] = useState(0);
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState<Page[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    setText('');
    setCursor(0);
    setAnswer('');
    setCitations([]);
    setError(null);
    const id = window.setTimeout(() => inputRef.current?.focus(), 10);
    return () => window.clearTimeout(id);
  }, [open, mode]);

  const matches = useMemo(() => {
    const needle = text.trim().toLowerCase();
    const ranked = needle
      ? pages.filter(
          (page) =>
            page.title.toLowerCase().includes(needle) ||
            page.slug.toLowerCase().includes(needle),
        )
      : pages;
    return ranked.slice(0, 40);
  }, [pages, text]);

  useEffect(() => {
    setCursor(0);
  }, [text]);

  async function ask() {
    const question = text.trim();
    if (!question || asking) return;
    setAsking(true);
    setAnswer('');
    setCitations([]);
    setError(null);
    try {
      await query(
        question,
        (token) => setAnswer((prev) => prev + token),
        (next) => setCitations(next),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setAsking(false);
    }
  }

  function openMatch(page: Page) {
    onClose();
    navigate(`/wiki/${page.slug}`);
  }

  if (!open) return null;

  return (
    <div
      className="overlay on"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="sheet" role="dialog" aria-label={mode === 'ask' ? 'Ask Archivum' : 'Go to file'}>
        <div className="sheet-in">
          <Icon name={mode === 'ask' ? 'sparkles' : 'folder'} size={18} />
          {mode === 'file' && <span className="mode">Go to file</span>}
          <input
            ref={inputRef}
            value={text}
            autoComplete="off"
            placeholder={
              mode === 'ask' ? 'Ask anything about your vault…' : 'Type a file or folder name…'
            }
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown') {
                event.preventDefault();
                setCursor((c) => Math.min(c + 1, matches.length - 1));
              } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                setCursor((c) => Math.max(c - 1, 0));
              } else if (event.key === 'Enter') {
                event.preventDefault();
                if (mode === 'ask') void ask();
                else if (matches[cursor]) openMatch(matches[cursor]);
              }
            }}
          />
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => onModeChange(mode === 'ask' ? 'file' : 'ask')}
          >
            {mode === 'ask' ? 'Go to file' : 'Ask instead'}
          </button>
        </div>

        {mode === 'ask' && (answer || asking || error) && (
          <div className="answer">
            {error ? (
              <p style={{ color: 'var(--bad)' }}>{error}</p>
            ) : (
              <p>{answer || 'Reading your notes…'}</p>
            )}
            {citations.length > 0 && (
              <div className="srcs">
                {citations.map((page, index) => (
                  <button key={page.slug} type="button" className="s" onClick={() => openMatch(page)}>
                    <span className="cite">{index + 1}</span>
                    {page.title || page.slug}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {mode === 'file' && (
          <div className="sheet-list">
            {matches.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 'var(--t-13)' }}>
                Nothing matches.
              </div>
            ) : (
              matches.map((page, index) => (
                <button
                  key={page.slug}
                  type="button"
                  className={cn('sheet-item', index === cursor && 'on')}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => openMatch(page)}
                >
                  <Icon name="file" />
                  <span>{page.title || page.slug}</span>
                  <span className="pathsub">{page.slug}</span>
                </button>
              ))
            )}
          </div>
        )}

        <div className="sheet-foot">
          <span>
            <span className="kbd">↑↓</span> move
          </span>
          <span>
            <span className="kbd">↵</span> {mode === 'ask' ? 'ask' : 'open'}
          </span>
          <span>
            <span className="kbd">⌘P</span> go to file
          </span>
          <span style={{ marginLeft: 'auto' }}>
            <span className="kbd">esc</span> close
          </span>
        </div>
      </div>
    </div>
  );
}
