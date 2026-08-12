import { X } from 'lucide-react';
import type { Citation, ContextNode } from '../api';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';

type ProvenanceDrawerProps = {
  open: boolean;
  onClose: () => void;
  citations: Citation[];
  extractionMethod?: ContextNode['extraction_method'] | 'DERIVED' | null;
  confidence?: number | null;
  onCitationClick?: (citation: Citation) => void;
};

export function ProvenanceDrawer({
  open,
  onClose,
  citations,
  extractionMethod,
  confidence,
  onCitationClick,
}: ProvenanceDrawerProps) {
  if (!open) return null;

  return (
    <aside
      className="absolute inset-y-0 right-0 z-20 flex w-full max-w-sm flex-col border-l border-white/[0.08] bg-[#1a1a1a] shadow-2xl"
      aria-label="Evidence and citations"
    >
      <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] p-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Evidence</h3>
          <p className="mt-1 text-xs text-muted-foreground">Citations supporting this context.</p>
        </div>
        <Button type="button" variant="ghost" size="icon" title="Close evidence" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-white/[0.08] p-4">
        {extractionMethod && <Badge variant="outline">{extractionMethod}</Badge>}
        {confidence !== null && confidence !== undefined && (
          <Badge variant="secondary">{`${Math.round(confidence * 100)}%`}</Badge>
        )}
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
        {citations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No citations are available for this context.</p>
        ) : citations.map((citation, index) => (
          <button
            key={`${citation.source_id}:${citation.chunk_id}:${citation.span_start ?? index}`}
            type="button"
            className="block w-full rounded-[5px] border border-white/[0.08] bg-white/[0.03] p-3 text-left transition-colors hover:bg-white/[0.07]"
            onClick={() => onCitationClick?.(citation)}
          >
            <div className="truncate text-xs font-medium text-zinc-200">{citation.source_id}</div>
            {citation.quote && <p className="mt-2 text-sm leading-5 text-zinc-300">{citation.quote}</p>}
            <div className="mt-2 text-[11px] text-muted-foreground">{citation.chunk_id}</div>
          </button>
        ))}
      </div>
    </aside>
  );
}
