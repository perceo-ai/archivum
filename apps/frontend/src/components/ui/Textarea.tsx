import * as React from 'react';
import { cn } from '../../lib/cn';

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        'soft-border flex min-h-[120px] w-full rounded-[5px] border bg-white/[0.05] px-3 py-2 text-sm text-white shadow-none',
        'placeholder:text-zinc-400',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  );
}
