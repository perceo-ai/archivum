import { useAppState, useAppDispatch } from '../store';
import { useNavigate, useLocation } from 'react-router-dom';
import FileTree from './FileTree';
import BacklinksPanel from './BacklinksPanel';
import StatusBar from './StatusBar';
import { Button } from './ui/Button';

interface LayoutProps {
  children: React.ReactNode;
}

type NavItem = {
  label: string;
  path: string;
  view: 'editor' | 'graph' | 'query' | 'ingest' | 'search';
};

const NAV_ITEMS: NavItem[] = [
  { label: 'Wiki', path: '/wiki', view: 'editor' },
  { label: 'Graph', path: '/graph', view: 'graph' },
  { label: 'Query', path: '/query', view: 'query' },
  { label: 'Ingest', path: '/ingest', view: 'ingest' },
  { label: 'Search', path: '/search', view: 'search' },
];

export default function Layout({ children }: LayoutProps) {
  const { leftOpen, rightOpen, currentSlug } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();

  const currentPath = location.pathname;

  function isActive(item: NavItem) {
    if (item.view === 'editor') return currentPath.startsWith('/wiki/');
    return currentPath === item.path;
  }

  function handleNav(item: NavItem) {
    dispatch({ type: 'SET_ACTIVE_VIEW', view: item.view });
    if (item.view === 'editor') {
      // Navigate to current page or just /wiki base
      navigate(currentSlug ? `/wiki/${currentSlug}` : '/');
    } else {
      navigate(item.path);
    }
  }

  return (
    <div className="flex flex-col h-screen bg-bg overflow-hidden">
      {/* Top bar */}
      <header
        className="flex items-center gap-6 px-4 h-12 shrink-0 border-b border-border bg-panel/30 backdrop-blur supports-[backdrop-filter]:bg-panel/20"
      >
        <span className="text-foreground font-semibold text-base tracking-wide select-none">
          Archivum
        </span>
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => (
            <Button
              key={item.path}
              onClick={() => handleNav(item)}
              variant={isActive(item) ? 'secondary' : 'ghost'}
              size="sm"
            >
              {item.label}
            </Button>
          ))}
        </nav>
        <div className="flex-1" />
        <Button
          onClick={() => dispatch({ type: 'TOGGLE_LEFT' })}
          variant="ghost"
          size="icon"
          title={leftOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          <SidebarLeftIcon />
        </Button>
        <Button
          onClick={() => dispatch({ type: 'TOGGLE_RIGHT' })}
          variant="ghost"
          size="icon"
          title={rightOpen ? 'Collapse panel' : 'Expand panel'}
        >
          <SidebarRightIcon />
        </Button>
      </header>

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <aside
          className="shrink-0 flex flex-col border-r border-border overflow-hidden transition-all duration-200 bg-panel/40 backdrop-blur supports-[backdrop-filter]:bg-panel/30"
          style={{ width: leftOpen ? '280px' : '0px' }}
        >
          {leftOpen && <FileTree />}
        </aside>

        {/* Center panel */}
        <main className="flex-1 overflow-hidden flex flex-col min-w-0">
          {children}
        </main>

        {/* Right sidebar */}
        <aside
          className="shrink-0 flex flex-col border-l border-border overflow-hidden transition-all duration-200 bg-panel/40 backdrop-blur supports-[backdrop-filter]:bg-panel/30"
          style={{ width: rightOpen ? '280px' : '0px' }}
        >
          {rightOpen && <BacklinksPanel />}
        </aside>
      </div>

      {/* Status bar */}
      <StatusBar />
    </div>
  );
}

function SidebarLeftIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <path d="M2 2h3v12H2V2zm4 0h8v12H6V2zM1 1v14h14V1H1z" />
    </svg>
  );
}

function SidebarRightIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <path d="M11 2h3v12h-3V2zm-9 0h8v12H2V2zM1 1v14h14V1H1z" />
    </svg>
  );
}
