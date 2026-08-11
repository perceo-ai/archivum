import { useLocation, useNavigate } from 'react-router-dom';
import { cn } from '../lib/cn';
import GraphView from '../components/GraphView';
import IngestPanel from '../components/IngestPanel';
import QueryPanel from '../components/QueryPanel';
import LintPage from './LintPage';
import SettingsPage from './SettingsPage';

const ITEMS = [
  {
    slug: 'graph',
    label: 'Graph',
    title: 'Knowledge Graph',
    description: 'Explore entities, pages, and backlinks as a connected map.',
    render: (navigate: (slug: string) => void) => <GraphView onNavigate={navigate} />,
  },
  {
    slug: 'ingest',
    label: 'Ingest',
    title: 'Import',
    description: 'Add files and URLs to the vault while Archivum extracts pages and links.',
    render: () => <IngestPanel />,
  },
  {
    slug: 'query',
    label: 'Query',
    title: 'Ask Archivum',
    description: 'Answer questions from your notes with citations back to source pages.',
    render: () => <QueryPanel />,
  },
  {
    slug: 'lint',
    label: 'Lint',
    title: 'Vault Health',
    description: 'Find broken wikilinks, orphan pages, and repairable structure issues.',
    render: () => <LintPage />,
  },
  {
    slug: 'settings',
    label: 'Settings',
    title: 'Settings',
    description: 'Configure models, transcription support, and sharing access.',
    render: () => <SettingsPage />,
  },
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
          <div className="min-w-0 flex-1">
            <h2 className="text-3xl font-semibold tracking-tight text-foreground">{current.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {current.description}
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

      <div className="workspace-pane flex min-h-0 flex-1 overflow-hidden">
        {current.render((slug) => navigate(`/wiki/${slug}`))}
      </div>
    </div>
  );
}
