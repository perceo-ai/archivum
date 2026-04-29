import * as React from 'react';
import { cn } from '../../lib/cn';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'icon';

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
}) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium transition',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg',
        'disabled:opacity-50 disabled:pointer-events-none',
        variant === 'primary' &&
          'bg-accent text-accent-foreground hover:bg-accent/90 shadow-sm shadow-black/20',
        variant === 'secondary' &&
          'bg-muted/60 text-foreground border border-border hover:bg-muted/80',
        variant === 'ghost' && 'text-foreground/80 hover:bg-muted/50 hover:text-foreground',
        variant === 'danger' &&
          'bg-danger text-danger-foreground hover:bg-danger/90 shadow-sm shadow-black/20',
        size === 'md' && 'h-9 px-3 text-sm',
        size === 'sm' && 'h-8 px-2.5 text-xs',
        size === 'icon' && 'h-9 w-9',
        className,
      )}
      {...props}
    />
  );
}

