import { Copy, Link } from 'lucide-react';
import { useAppState } from '../store';
import { Button } from './ui/Button';

export default function NotesInteractionPanel() {
  const { currentSlug } = useAppState();

  async function copyLink(slug: string) {
    const url = `${window.location.origin}/wiki/${slug}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // best-effort fallback: silently no-op
    }
  }

  return (
    <div className="rounded-[6px] px-1 py-1">
      <div className="mb-1 flex items-center gap-2 px-1 text-xs font-medium text-muted-foreground">
        <Link className="h-3.5 w-3.5" />
        <span>Page</span>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => currentSlug && copyLink(currentSlug)}
        disabled={!currentSlug}
        className="h-8 w-full justify-start px-2 text-muted-foreground hover:text-foreground"
      >
        <Copy className="h-4 w-4" />
        Copy page link
      </Button>
    </div>
  );
}
