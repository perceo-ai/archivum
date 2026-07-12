import { useLocation, useNavigate } from 'react-router-dom';
import { cn } from '../lib/cn';
import GraphView from '../components/GraphView';
import IngestPanel from '../components/IngestPanel';
import QueryPanel from '../components/QueryPanel';
import LintPage from './LintPage';
import SettingsPage from './SettingsPage';

const ITEMS = [
  { slug: 'graph', label: 'Graph', render: (navigate: (slug: string) => void) => <GraphView onNavigate={navigate} /> },
  { slug: 'ingest', label: 'Ingest', render: () => <IngestPanel /> },
  { slug: 'query', label: 'Query', render: () => <QueryPanel /> },
  { slug: 'lint', label: 'Lint', render: () => <LintPage /> },
  { slug: 'settings', label: 'Settings', render: () => <SettingsPage /> },
];

export default function ToolsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const current = ITEMS.find((item) => location.pathname.endsWith(`/${item.slug}`)) ?? ITEMS[0];

  return (
    <div className="page-frame bg-transparent">
      <div className="page-header">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Tools
        </p>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight text-foreground">Utility surfaces, without shell clutter.</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Graph, ingest, query, lint, and settings stay available, but now they sit behind one cleaner tools workspace.
            </p>
          </div>
          <div className="section-tabs">
            {ITEMS.map((item) => (
              <button
                key={item.slug}
                type="button"
                className={cn('section-tab', current.slug === item.slug && 'section-tab-active')}
                onClick={() => navigate(`/tools/${item.slug}`)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden rounded-[28px] bg-transparent">
        {current.render((slug) => navigate(`/wiki/${slug}`))}
      </div>
    </div>
  );
}
