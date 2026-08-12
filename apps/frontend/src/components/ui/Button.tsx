import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/cn';

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[5px] text-sm font-medium transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    'disabled:pointer-events-none disabled:opacity-50',
    '[&_svg]:pointer-events-none [&_svg]:shrink-0',
  ].join(' '),
  {
    variants: {
      variant: {
        default: 'bg-gradient-to-b from-[#8b5cf6] to-[#7848e6] text-white shadow-none hover:from-[#7c3aed] hover:to-[#6d28d9]',
        secondary: 'soft-border border bg-white/[0.05] text-white shadow-none hover:bg-white/[0.08]',
        ghost: 'text-zinc-300 hover:bg-white/[0.08] hover:text-white',
        outline: 'soft-border border bg-transparent text-zinc-200 hover:bg-white/[0.08] hover:text-white',
        destructive: 'bg-[#f87171] text-[#161616] hover:bg-[#ef4444]',

        // backwards compat
        primary: 'bg-gradient-to-b from-[#8b5cf6] to-[#7848e6] text-white shadow-none hover:from-[#7c3aed] hover:to-[#6d28d9]',
        danger: 'bg-[#f87171] text-[#161616] hover:bg-[#ef4444]',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 px-3 text-xs',
        lg: 'h-10 px-8',
        icon: 'h-9 w-9',

        // backwards compat
        md: 'h-9 px-4 py-2',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
);

export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot : 'button';
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}
