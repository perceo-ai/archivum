import { useState } from 'react';
import { cn } from '../lib/cn';

/**
 * The Perceo mark.
 *
 * One component so every surface that shows the brand — the sidebar, the setup
 * flow, the login card — uses the same asset at the same treatment, and so a
 * missing file degrades to the lettermark instead of a broken image.
 *
 * The file lives in `public/`, which Vite copies verbatim into `dist/`, which
 * the frontend image serves from nginx. It is also the favicon.
 */

export const LOGO_SRC = '/perceo-logo.png';

export function BrandMark({
  size = 24,
  className,
}: {
  size?: number;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <span className={cn('brand-mark brand-mark-fallback', className)} style={{ width: size, height: size }}>
        A
      </span>
    );
  }

  return (
    <img
      src={LOGO_SRC}
      alt="Archivum"
      width={size}
      height={size}
      className={cn('brand-mark', className)}
      onError={() => setFailed(true)}
    />
  );
}
