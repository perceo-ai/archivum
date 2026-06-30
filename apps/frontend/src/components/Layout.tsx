import { useLocation, useNavigate } from 'react-router-dom';
import { BookOpen, Blocks, PanelRight, Search, Sparkles, Wrench, X } from 'lucide-react';
import { type ActiveView, useAppDispatch, useAppState } from '../store';
import { cn } from '../lib/cn';
import FileTree from './FileTree';
import RightSidebar from './RightSidebar';
import StatusBar from './StatusBar';
import { Button } from './ui/Button';

interface LayoutProps {
  children: React.ReactNode;
}

type NavItem = {
  label: string;
  path: string;
  view: ActiveView;
  icon: typeof BookOpen;
};

const NAV_ITEMS: NavItem[] = [
  { label: 'Library', path: '/library', view: 'library', icon: BookOpen },
  { label: 'Workflows', path: '/workflows/daily', view: 'workflows', icon: Blocks },
  { label: 'Tools', path: '/tools/graph', view: 'tools', icon: Wrench },
];

export default function Layout({ children }: LayoutProps) {
  const { leftOpen, rightOpen, currentSlug } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();

  const currentSection = location.pathname.startsWith('/workflows/')
    ? 'workflows'
    : location.pathname.startsWith('/tools/')
      ? 'tools'
      : 'library';

  function isActive(item: NavItem) {
    return currentSection === item.view;
  }

  function handleNav(item: NavItem) {
    dispatch({ type: 'SET_ACTIVE_VIEW', view: item.view });
    if (item.view === 'library') {
      navigate(currentSlug ? `/wiki/${currentSlug}` : item.path);
      return;
    }
    navigate(item.path);
  }

  return (
    <div className="app-shell flex h-screen overflow-hidden">
      <aside className="rail-panel hidden w-[84px] shrink-0 flex-col items-center px-3 py-4 text-white md:flex">
        <button
          type="button"
          className="mb-6 flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-sm font-extrabold tracking-[0.12em] text-white"
          onClick={() => navigate(currentSlug ? `/wiki/${currentSlug}` : '/library')}
          title="Archivum"
        >
          AR
        </button>

        <nav className="flex flex-col gap-2">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.path}
              type="button"
              onClick={() => handleNav(item)}
              title={item.label}
              className={cn(
                'flex h-12 w-12 items-center justify-center rounded-2xl transition-colors',
                isActive(item) ? 'bg-primary text-primary-foreground shadow-lg' : 'bg-white/5 text-white/76 hover:bg-white/12',
              )}
            >
              <item.icon className="h-5 w-5" />
            </button>
          ))}
        </nav>

        <div className="mt-auto flex flex-col gap-2">
          <button
            type="button"
            title={leftOpen ? 'Close vault' : 'Open vault'}
            onClick={() => dispatch({ type: 'TOGGLE_LEFT' })}
            className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 text-white/76 transition-colors hover:bg-white/12"
          >
            <BookOpen className="h-5 w-5" />
          </button>
          <button
            type="button"
            title={rightOpen ? 'Hide inspector' : 'Show inspector'}
            onClick={() => dispatch({ type: 'TOGGLE_RIGHT' })}
            className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 text-white/76 transition-colors hover:bg-white/12"
          >
            <PanelRight className="h-5 w-5" />
          </button>
        </div>
      </aside>

      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-border/80 bg-background/75 px-4 backdrop-blur md:px-6">
          <Button
            onClick={() => dispatch({ type: 'TOGGLE_LEFT' })}
            variant="secondary"
            size="sm"
            className="md:hidden"
          >
            Vault
          </Button>

          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Archivum
            </p>
            <h1 className="truncate text-base font-semibold text-foreground">
              {currentSection === 'library' ? 'Library' : currentSection === 'workflows' ? 'Workflows' : 'Tools'}
            </h1>
          </div>

          <button
            type="button"
            onClick={() => navigate('/library')}
            className="surface-panel ml-2 hidden min-w-[240px] items-center gap-3 rounded-2xl px-4 py-2 text-left text-sm text-muted-foreground md:flex"
          >
            <Search className="h-4 w-4" />
            <span>Search pages, notes, and context</span>
            <span className="ml-auto rounded-lg bg-secondary px-2 py-1 text-[11px] font-semibold text-secondary-foreground">
              /
            </span>
          </button>

          <div className="ml-auto flex items-center gap-2">
            <Button onClick={() => dispatch({ type: 'TOGGLE_LEFT' })} variant="ghost" size="sm">
              <BookOpen className="h-4 w-4" />
              Vault
            </Button>
            <Button onClick={() => navigate('/workflows/daily')} variant="ghost" size="sm">
              <Sparkles className="h-4 w-4" />
              Resume
            </Button>
            <Button
              onClick={() => dispatch({ type: 'TOGGLE_RIGHT' })}
              variant="ghost"
              size="icon"
              title={rightOpen ? 'Hide inspector' : 'Show inspector'}
            >
              <PanelRight className="h-4 w-4" />
            </Button>
          </div>
        </header>

        <div className="relative flex min-h-0 flex-1 overflow-hidden">
          <aside
            className={cn(
              'surface-panel absolute inset-y-4 left-4 z-20 flex w-[320px] flex-col overflow-hidden rounded-[28px] transition-transform duration-200',
              leftOpen ? 'translate-x-0' : '-translate-x-[120%]',
            )}
          >
            <div className="flex items-center justify-between border-b border-border/80 px-4 py-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Library
                </p>
                <p className="text-sm font-semibold text-foreground">Vault drawer</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => dispatch({ type: 'TOGGLE_LEFT' })}
                title="Close vault"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <FileTree />
          </aside>

          {leftOpen && (
            <button
              type="button"
              aria-label="Close vault drawer"
              className="absolute inset-0 z-10 bg-black/10"
              onClick={() => dispatch({ type: 'TOGGLE_LEFT' })}
            />
          )}

          <main className="page-frame min-w-0 overflow-hidden">
            <div className="surface-panel flex min-h-0 flex-1 overflow-hidden rounded-[32px]">
              {children}
            </div>
          </main>

          {rightOpen && (
            <aside className="hidden w-[320px] shrink-0 border-l border-border/80 bg-background/55 xl:flex">
              <RightSidebar />
            </aside>
          )}
        </div>

        <StatusBar />
      </div>
    </div>
  );
}
