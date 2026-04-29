import * as React from 'react';
import { cn } from '../../lib/cn';

type Variant = 'default' | 'info' | 'success' | 'warning' | 'danger';

export function Badge({
  variant = 'default',
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: Variant }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none',
        variant === 'default' && 'border-border/60 bg-muted/40 text-foreground/80',
        variant === 'info' && 'border-accent/30 bg-accent/10 text-accent',
        variant === 'success' && 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300',
        variant === 'warning' && 'border-amber-300/25 bg-amber-300/10 text-amber-200',
        variant === 'danger' && 'border-danger/25 bg-danger/10 text-danger',
        className,
      )}
      {...props}
    />
  );
}

