import { useState } from 'react';
import BacklinksPanel from './BacklinksPanel';
import NotesInteractionPanel from './NotesInteractionPanel';
import { Button } from './ui/Button';

export default function RightSidebar() {
  const [tab, setTab] = useState<'backlinks' | 'notes'>('backlinks');

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-border shrink-0">
        <div className="flex gap-1">
          <Button
            variant={tab === 'backlinks' ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setTab('backlinks')}
          >
            Linked from
          </Button>
          <Button
            variant={tab === 'notes' ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setTab('notes')}
          >
            Notes actions
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        {tab === 'backlinks' ? <BacklinksPanel /> : <NotesInteractionPanel />}
      </div>
    </div>
  );
}
