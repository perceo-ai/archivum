import { useNavigate } from 'react-router-dom';
import SearchBar from '../components/SearchBar';
import { Button } from '../components/ui/Button';

export default function LibraryPage() {
  const navigate = useNavigate();

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
              Browse the vault, search across notes, and open the context you need.
            </p>
          </div>
          <Button variant="secondary" onClick={() => navigate('/workflows/daily')}>
            Resume daily workflow
          </Button>
        </div>
      </div>

      <div className="workspace-pane flex min-h-0 flex-1 overflow-hidden">
        <SearchBar />
      </div>
    </div>
  );
}
