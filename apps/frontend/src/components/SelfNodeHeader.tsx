import { Badge } from './ui/Badge';

export function SelfNodeHeader({ label = 'Me', activeScope }: { label?: string; activeScope: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2" aria-label="Current graph center">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-amber-300/40 bg-amber-300/15 text-xs font-semibold text-amber-100">
        {label.slice(0, 1).toUpperCase()}
      </div>
      <div className="min-w-0 leading-tight">
        <div className="truncate text-sm font-semibold text-foreground">{label}</div>
        <div className="truncate text-[11px] text-muted-foreground">{activeScope}</div>
      </div>
      <Badge variant="secondary" className="shrink-0">Center</Badge>
    </div>
  );
}
