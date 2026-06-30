import BacklinksPanel from './BacklinksPanel';
import NotesInteractionPanel from './NotesInteractionPanel';

export default function RightSidebar() {
  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto px-4 py-4">
      <div className="rounded-2xl border border-border/80 bg-card/80 p-3 shadow-sm">
        <p className="mb-3 text-sm font-semibold text-foreground">Linked from</p>
        <BacklinksPanel />
      </div>

      <div className="rounded-2xl border border-border/80 bg-card/80 p-3 shadow-sm">
        <p className="mb-3 text-sm font-semibold text-foreground">Notes actions</p>
        <NotesInteractionPanel />
      </div>
    </div>
  );
}
