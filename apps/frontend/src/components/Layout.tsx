import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { BookOpen, Blocks, PanelRight, Search, Sparkles, Wrench, X } from 'lucide-react';
import { type ActiveView, useAppDispatch, useAppState } from '../store';
import { cn } from '../lib/cn';
import FileTree from './FileTree';
import QuickSearchModal from './QuickSearchModal';
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
  const [searchOpen, setSearchOpen] = useState(false);

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

  useEffect(() => {
    function shouldIgnoreShortcut(target: EventTarget | null) {
      if (!(target instanceof HTMLElement)) return false;
      return (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable ||
        target.closest('[cmdk-input-wrapper]') !== null
      );
    }

    function handleKeydown(event: KeyboardEvent) {
      if (shouldIgnoreShortcut(event.target)) return;
      if (event.key === '/' || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k')) {
        event.preventDefault();
        setSearchOpen(true);
      }
    }

    function handleOpenSearch() {
      setSearchOpen(true);
    }

    window.addEventListener('keydown', handleKeydown);
    window.addEventListener('archivum:open-search', handleOpenSearch);
    return () => {
      window.removeEventListener('keydown', handleKeydown);
      window.removeEventListener('archivum:open-search', handleOpenSearch);
    };
  }, []);

  return (
    <div className="perceo-shell grid-lines flex h-screen overflow-hidden">
      <aside className="rail-panel hidden w-[72px] shrink-0 flex-col items-center px-3 py-4 text-white md:flex">
        <button
          type="button"
          className="soft-border mb-6 flex h-11 w-11 items-center justify-center rounded-[8px] border bg-white/[0.05] font-serif text-xl font-bold italic tracking-tight text-white transition-colors hover:bg-white/[0.08]"
          onClick={() => navigate(currentSlug ? `/wiki/${currentSlug}` : '/library')}
          title="Archivum"
        >
          A
        </button>

        <nav className="flex flex-col gap-2">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.path}
              type="button"
              onClick={() => handleNav(item)}
              title={item.label}
              className={cn(
                'flex h-11 w-11 items-center justify-center rounded-[8px] transition-colors',
                isActive(item)
                  ? 'bg-gradient-to-b from-[#8b5cf6] to-[#7848e6] text-white'
                  : 'bg-white/[0.04] text-zinc-400 hover:bg-white/[0.08] hover:text-white',
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
            className="flex h-11 w-11 items-center justify-center rounded-[8px] bg-white/[0.04] text-zinc-400 transition-colors hover:bg-white/[0.08] hover:text-white"
          >
            <BookOpen className="h-5 w-5" />
          </button>
          <button
            type="button"
            title={rightOpen ? 'Hide inspector' : 'Show inspector'}
            onClick={() => dispatch({ type: 'TOGGLE_RIGHT' })}
            className="flex h-11 w-11 items-center justify-center rounded-[8px] bg-white/[0.04] text-zinc-400 transition-colors hover:bg-white/[0.08] hover:text-white"
          >
            <PanelRight className="h-5 w-5" />
          </button>
        </div>
      </aside>

      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="subtle-divider flex h-14 shrink-0 items-center gap-3 border-b bg-[#161616]/85 px-3 backdrop-blur md:px-5">
          <Button
            onClick={() => dispatch({ type: 'TOGGLE_LEFT' })}
            variant="secondary"
            size="sm"
            className="md:hidden"
          >
            Vault
          </Button>

          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Archivum
            </p>
            <h1 className="truncate text-base font-semibold text-white">
              {currentSection === 'library' ? 'Library' : currentSection === 'workflows' ? 'Workflows' : 'Tools'}
            </h1>
          </div>

          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className="soft-border ml-2 hidden min-w-[260px] items-center gap-3 rounded-[5px] border bg-white/[0.05] px-4 py-2 text-left text-sm text-zinc-400 transition-colors hover:bg-white/[0.08] hover:text-white md:flex"
          >
            <Search className="h-4 w-4" />
            <span>Search notes</span>
            <span className="soft-border ml-auto rounded-[5px] border bg-white/[0.05] px-2 py-1 text-[11px] font-semibold text-zinc-300">
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
              'vault-sidebar surface-panel absolute inset-y-3 left-3 z-20 flex w-[320px] flex-col overflow-hidden rounded-[8px] transition-transform duration-200 md:static md:inset-auto md:z-auto md:w-[300px] md:rounded-none md:border-y-0 md:border-l-0 md:bg-[#171616]/70 md:transition-none lg:w-[340px]',
              leftOpen ? 'translate-x-0' : '-translate-x-[120%] md:hidden',
            )}
          >
            <div className="subtle-divider flex items-center justify-between border-b px-4 py-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Library
                </p>
                <p className="text-sm font-semibold text-white">Vault</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => dispatch({ type: 'TOGGLE_LEFT' })}
                title="Close vault"
                className="md:hidden"
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
              className="absolute inset-0 z-10 bg-black/40 md:hidden"
              onClick={() => dispatch({ type: 'TOGGLE_LEFT' })}
            />
          )}

          <main className="min-w-0 flex-1 overflow-hidden">
            {children}
          </main>

          {rightOpen && (
            <aside className="subtle-divider hidden w-[320px] shrink-0 border-l bg-[#171616]/70 xl:flex">
              <RightSidebar />
            </aside>
          )}
        </div>

        <StatusBar />
      </div>
      <QuickSearchModal open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  );
}
