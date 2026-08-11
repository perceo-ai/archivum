import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/cn';

const badgeVariants = cva(
  'inline-flex items-center rounded-[5px] border px-2 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-white hover:bg-primary/80',
        secondary: 'border-white/10 bg-white/[0.05] text-zinc-200 hover:bg-white/[0.08]',
        outline: 'border-white/10 text-zinc-200',
        destructive: 'border-transparent bg-[#f87171] text-[#161616] hover:bg-[#ef4444]',

        // backwards compat
        info: 'border-white/10 bg-white/[0.05] text-zinc-200',
        success: 'border-transparent bg-emerald-600 text-white',
        warning: 'border-transparent bg-amber-500 text-black',
        danger: 'border-transparent bg-destructive text-destructive-foreground',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export function Badge({
  variant,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof badgeVariants>) {
  return (
    <div className={cn(badgeVariants({ variant, className }))} {...props} />
  );
}
