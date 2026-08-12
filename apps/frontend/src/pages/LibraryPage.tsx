import { useNavigate } from 'react-router-dom';
import { Archive, CalendarDays, FolderOpen, Inbox, Search } from 'lucide-react';
import { Button } from '../components/ui/Button';

const SECTIONS = [
  { name: 'Inbox', path: 'inbox', description: 'New captures and unsorted notes.', icon: Inbox },
  { name: 'Notes', path: 'notes', description: 'Durable knowledge and evergreen writing.', icon: FolderOpen },
  { name: 'Daily', path: 'daily', description: 'Journal entries and working logs.', icon: CalendarDays },
  { name: 'Archive', path: 'archive', description: 'Older material kept out of active navigation.', icon: Archive },
];

export default function LibraryPage() {
  const navigate = useNavigate();

  function openSearch() {
    window.dispatchEvent(new Event('archivum:open-search'));
  }

  return (
    <div className="page-frame bg-transparent">
      <div className="page-header">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Library
        </p>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-3xl font-semibold tracking-tight text-foreground">Library</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Vault navigation, saved notes, and source material.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={openSearch}>
              <Search className="h-4 w-4" />
              Search notes
            </Button>
            <Button variant="secondary" onClick={() => navigate('/workflows/daily')}>
              Resume daily
            </Button>
          </div>
        </div>
      </div>

      <div className="workspace-pane flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="subtle-divider border-b px-5 py-4">
          <h3 className="text-sm font-semibold text-foreground">Vault Structure</h3>
        </div>
        <div className="grid gap-0 divide-y divide-white/[0.06]">
          {SECTIONS.map((section) => (
            <div key={section.path} className="flex items-center gap-4 px-5 py-4">
              <section.icon className="h-4 w-4 shrink-0 text-zinc-500" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-foreground">{section.name}</div>
                <div className="mt-1 text-xs leading-5 text-muted-foreground">{section.description}</div>
              </div>
              <span className="text-xs text-zinc-500">{section.path}/</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
