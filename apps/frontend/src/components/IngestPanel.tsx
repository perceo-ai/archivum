import { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch } from '../store';
import { ingestFile, ingestUrl, listPages, openIngestSocket } from '../api';
import type { IngestLog, IngestProgress, IngestSocketMessage } from '../types';
import { Button } from './ui/Button';
import { Card } from './ui/Card';
import { Input } from './ui/Input';
import { cn } from '../lib/cn';

interface FileStatus {
  ingestId?: number;
  name: string;
  events: IngestProgress[];
  done: boolean;
  error: string | null;
  fromHistory?: boolean;
}

const ACCEPTED_TYPES = ['.md', '.txt', '.pdf', '.html', '.docx'];

export default function IngestPanel() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [dragOver, setDragOver] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [fileStatuses, setFileStatuses] = useState<FileStatus[]>([]);
  const [processing, setProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const updateFileStatus = useCallback((name: string, event: IngestProgress) => {
    setFileStatuses((prev) =>
      {
        const sourceName = event.file ?? event.source ?? name;
        let matched = false;
        const next = prev.map((fs) => {
          if (fs.name !== name && fs.name !== sourceName && (event.log_id === undefined || fs.ingestId !== event.log_id)) {
            return fs;
          }
          matched = true;
          return {
            ...fs,
            ingestId: event.log_id ?? fs.ingestId,
            name: sourceName,
            events: [...fs.events, event],
            done: event.type === 'done' || event.type === 'error',
            error: event.type === 'error' ? (event.message ?? 'Unknown error') : fs.error,
          };
        });

        if (matched) return next;

        return [
          ...next,
          {
            ingestId: event.log_id,
            name: sourceName,
            events: [event],
            done: event.type === 'done' || event.type === 'error',
            error: event.type === 'error' ? (event.message ?? 'Unknown error') : null,
            fromHistory: true,
          },
        ];
      },
    );
  }, []);

  const mergeIngestLogs = useCallback((logs: IngestLog[]) => {
    setFileStatuses((prev) => {
      const next = [...prev];

      for (const log of logs) {
        const existingIndex = next.findIndex(
          (fs) => fs.ingestId === log.id || fs.name === log.source_path,
        );
        const isDone = log.status === 'done' || log.status === 'error';
        const finalEvent: IngestProgress | null =
          log.status === 'done'
            ? {
                type: 'done',
                file: log.source_path,
                log_id: log.id,
                pages_created: log.pages_created,
                pages_updated: log.pages_updated,
              }
            : log.status === 'error'
              ? {
                  type: 'error',
                  file: log.source_path,
                  log_id: log.id,
                  message: log.error ?? 'Unknown error',
                }
              : null;

        if (existingIndex === -1) {
          next.push({
            ingestId: log.id,
            name: log.source_path,
            events: finalEvent
              ? [
                  { type: 'start', file: log.source_path, log_id: log.id },
                  finalEvent,
                ]
              : [{ type: 'start', file: log.source_path, log_id: log.id }],
            done: isDone,
            error: log.status === 'error' ? (log.error ?? 'Unknown error') : null,
            fromHistory: true,
          });
          continue;
        }

        const existing = next[existingIndex];
        const hasFinalEvent = existing.events.some((event) =>
          log.status === 'done' ? event.type === 'done' : event.type === 'error',
        );

        next[existingIndex] = {
          ...existing,
          ingestId: log.id,
          name: log.source_path,
          done: isDone ? true : existing.done,
          error: log.status === 'error' ? (log.error ?? 'Unknown error') : existing.error,
          events: finalEvent && !hasFinalEvent
            ? [...existing.events, finalEvent]
            : existing.events,
        };
      }

      return next;
    });
  }, []);

  useEffect(() => {
    function handleSocketMessage(message: IngestSocketMessage) {
      if (message.type === 'snapshot') {
        mergeIngestLogs(message.logs);
      } else if (message.type === 'event') {
        const event = message.event;
        updateFileStatus(event.file ?? event.source ?? 'Ingest task', event);
        if (event.type === 'done') {
          listPages()
            .then((pages) => dispatch({ type: 'SET_PAGES', pages }))
            .catch(() => undefined);
        }
      }
    }

    const socket = openIngestSocket(handleSocketMessage);
    return () => socket.close();
  }, [dispatch, mergeIngestLogs, updateFileStatus]);

  const processFiles = useCallback(
    async (files: File[]) => {
      setProcessing(true);

      // Initialize statuses
      setFileStatuses((prev) => [
        ...prev,
        ...files.map((f) => ({
          name: f.name,
          events: [{ type: 'start' as const, file: f.name, message: 'Uploading' }],
          done: false,
          error: null,
        })),
      ]);

      await Promise.allSettled(
        files.map(async (file) => {
          try {
            await ingestFile(file);
          } catch (err) {
            updateFileStatus(file.name, {
              type: 'error',
              file: file.name,
              message: (err as Error).message,
            });
          }
        }),
      );

      // Refresh pages list
      try {
        const pages = await listPages();
        dispatch({ type: 'SET_PAGES', pages });
      } catch {
        // ignore
      }

      setProcessing(false);
    },
    [dispatch, updateFileStatus],
  );

  async function handleUrlIngest(e: React.FormEvent) {
    e.preventDefault();
    if (!urlInput.trim() || processing) return;

    const url = urlInput.trim();
    const name = url;
    setUrlInput('');
    setProcessing(true);
    setFileStatuses((prev) => [
      ...prev,
      { name, events: [{ type: 'start', file: name }], done: false, error: null },
    ]);

    try {
      await ingestUrl(url);
    } catch (err) {
      updateFileStatus(name, {
        type: 'error',
        message: (err as Error).message,
      });
    } finally {
      setProcessing(false);
    }
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(true);
  }

  function onDragLeave(e: React.DragEvent) {
    // Only leave if actually leaving the dropzone
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) {
      setDragOver(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      processFiles(Array.from(e.dataTransfer.files));
    }
  }

  function clearCompleted() {
    setFileStatuses((prev) => prev.filter((fs) => !fs.done));
  }

  const doneCount = fileStatuses.filter((fs) => fs.done).length;
  const totalPages = fileStatuses.reduce((sum, fs) => {
    const done = fs.events.find((e) => e.type === 'done');
    return sum + (done?.pages_created ?? 0) + (done?.pages_updated ?? 0);
  }, 0);

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-bg">
      <div className="max-w-2xl mx-auto w-full p-6 flex flex-col gap-6">
        <div>
          <h2 className="text-lg font-semibold text-foreground mb-1">Ingest Content</h2>
          <p className="text-sm text-muted-foreground">
            Import files or URLs into your knowledge base.
          </p>
        </div>

        {/* Drop zone */}
        <Card
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            'relative border-2 border-dashed cursor-pointer transition-colors p-10 text-center',
            dragOver ? 'border-accent/60 bg-accent/5' : 'border-border/60',
          )}
        >
          <UploadIcon className="mx-auto mb-3 text-text-muted w-10 h-10" />
          <p className="text-text-secondary text-sm font-medium">
            {dragOver ? 'Drop to ingest' : 'Drag & drop files here'}
          </p>
          <p className="text-muted-foreground text-xs mt-1">or click to browse</p>
          <p className="text-muted-foreground text-xs mt-3">
            Accepted: {ACCEPTED_TYPES.join(', ')}
          </p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED_TYPES.join(',')}
            className="hidden"
            onChange={(e) => e.target.files && processFiles(Array.from(e.target.files))}
          />
        </Card>

        {/* URL input */}
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Or import a URL
          </p>
          <form onSubmit={handleUrlIngest} className="flex gap-2">
            <Input
              type="url"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              placeholder="https://example.com/article"
            />
            <Button
              type="submit"
              variant="primary"
              disabled={processing || !urlInput.trim()}
            >
              Import
            </Button>
          </form>
        </div>

        {/* Progress section */}
        {fileStatuses.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                Progress
                {doneCount > 0 && ` — ${doneCount}/${fileStatuses.length} complete`}
                {totalPages > 0 && ` · ${totalPages} pages`}
              </p>
              {doneCount > 0 && (
                <button
                  onClick={clearCompleted}
                  className="text-xs text-text-muted hover:text-text-secondary transition-colors"
                >
                  Clear completed
                </button>
              )}
            </div>
            <div
              className="rounded-lg border divide-y overflow-hidden"
              style={{ borderColor: '#3a3a4a' }}
            >
              {fileStatuses.map((fs, i) => (
                <FileStatusRow
                  key={fs.ingestId ?? `${fs.name}-${i}`}
                  status={fs}
                  onNavigate={(slug) => navigate(`/wiki/${slug}`)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FileStatusRow({
  status,
  onNavigate,
}: {
  status: FileStatus;
  onNavigate: (slug: string) => void;
}) {
  const { name, events, done, error } = status;

  return (
    <div className="px-4 py-3" style={{ backgroundColor: '#252535' }}>
      <div className="flex items-start gap-2">
        <StatusDot done={done} error={!!error} processing={!done && events.length > 0} />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-text-primary font-medium truncate">{name}</p>
          {/* Event feed */}
          <div className="mt-1 space-y-0.5">
            {events.map((ev, i) => (
              <EventLine key={i} event={ev} onNavigate={onNavigate} />
            ))}
          </div>
          {!done && events.length === 0 && (
            <p className="text-xs text-text-muted mt-1">Pending...</p>
          )}
        </div>
        {done && !error && (
          <span className="shrink-0 text-xs text-green-400">✓</span>
        )}
        {error && (
          <span className="shrink-0 text-xs text-red-400">✗</span>
        )}
      </div>
    </div>
  );
}

function EventLine({
  event,
  onNavigate,
}: {
  event: IngestProgress;
  onNavigate: (slug: string) => void;
}) {
  const base = 'text-xs';

  switch (event.type) {
    case 'start':
      return <p className={`${base} text-text-muted`}>{event.message ?? 'Starting...'}</p>;
    case 'parsed':
      return (
        <p className={`${base} text-text-muted`}>
          Parsed content{event.chars ? ` · ${event.chars.toLocaleString()} chars` : ''}
        </p>
      );
    case 'extracting':
      return (
        <p className={`${base} text-text-muted`}>
          {event.message ?? 'Running LLM extraction...'}
        </p>
      );
    case 'extracted':
      return (
        <p className={`${base} text-text-muted`}>
          Extracted {event.pages ?? 0} pages and {event.entities ?? 0} entities
        </p>
      );
    case 'page_created':
      return (
        <p className={`${base} text-green-400`}>
          Created{' '}
          {event.slug ? (
            <button
              onClick={() => onNavigate(event.slug!)}
              className="underline hover:text-green-300"
            >
              {event.title ?? event.slug}
            </button>
          ) : (
            event.title
          )}
        </p>
      );
    case 'page_updated':
      return (
        <p className={`${base} text-accent`}>
          Updated{' '}
          {event.slug ? (
            <button
              onClick={() => onNavigate(event.slug!)}
              className="underline hover:text-blue-300"
            >
              {event.title ?? event.slug}
            </button>
          ) : (
            event.title
          )}
        </p>
      );
    case 'done':
      return (
        <p className={`${base} text-green-400 font-medium`}>
          Done — {event.pages_created ?? 0} created, {event.pages_updated ?? 0} updated
        </p>
      );
    case 'error':
      return <p className={`${base} text-red-400`}>Error: {event.message}</p>;
    default:
      return null;
  }
}

function StatusDot({
  done,
  error,
  processing,
}: {
  done: boolean;
  error: boolean;
  processing: boolean;
}) {
  if (error)
    return <span className="mt-1 w-2 h-2 rounded-full shrink-0 bg-red-400" />;
  if (done)
    return <span className="mt-1 w-2 h-2 rounded-full shrink-0 bg-green-400" />;
  if (processing)
    return <span className="mt-1 w-2 h-2 rounded-full shrink-0 bg-accent animate-pulse" />;
  return <span className="mt-1 w-2 h-2 rounded-full shrink-0 bg-text-muted" />;
}

function UploadIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}
