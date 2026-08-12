import BacklinksPanel from './BacklinksPanel';
import NotesInteractionPanel from './NotesInteractionPanel';

export default function RightSidebar() {
  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto px-4 py-4">
      <section className="min-h-0">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold text-foreground">Linked from</p>
          <span className="soft-border rounded-[5px] border bg-white/[0.05] px-2 py-1 text-[11px] font-semibold text-zinc-300">
            Backlinks
          </span>
        </div>
        <BacklinksPanel />
      </section>

      <section className="subtle-divider border-t pt-4">
        <p className="mb-3 text-sm font-semibold text-foreground">Notes actions</p>
        <NotesInteractionPanel />
      </section>
    </div>
  );
}
