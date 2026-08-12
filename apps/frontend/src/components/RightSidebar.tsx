import { Link2 } from 'lucide-react';
import BacklinksPanel from './BacklinksPanel';
import NotesInteractionPanel from './NotesInteractionPanel';

export default function RightSidebar() {
  return (
    <div className="flex h-full flex-col overflow-y-auto px-3 py-3">
      <section className="shrink-0 pb-3">
        <NotesInteractionPanel />
      </section>

      <section className="min-h-0 flex-1 pt-1">
        <div className="mb-2 flex items-center gap-2 px-1 text-xs font-medium text-muted-foreground">
          <Link2 className="h-3.5 w-3.5" />
          <span>Backlinks</span>
        </div>
        <BacklinksPanel />
      </section>
    </div>
  );
}
