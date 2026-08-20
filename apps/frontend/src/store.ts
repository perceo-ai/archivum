import React, { createContext, useContext, useReducer } from 'react';
import type { Page } from './types';

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';
export type ActiveView =
  | 'home'
  | 'editor'
  | 'library'
  | 'review'
  | 'topics'
  | 'people'
  | 'repos'
  | 'sources'
  | 'workflows'
  | 'tools'
  | 'graph'
  | 'query'
  | 'ingest'
  | 'search'
  | 'lint'
  | 'daily'
  | 'projects'
  | 'tasks'
  | 'decisions'
  | 'activity'
  | 'settings';

interface AppState {
  pages: Page[];
  pagesLoaded: boolean;
  currentSlug: string | null;
  saveStatus: SaveStatus;
  activeView: ActiveView;
  quickSearchOpen: boolean;
  leftOpen: boolean;
  rightOpen: boolean;
  isAuthenticated: boolean;
  theme: Theme;
}

export type Theme = 'dark' | 'light';

// Dark is the default. The choice is remembered per browser, and applied to
// <html data-theme> so the token layer can swap in one place.
const THEME_KEY = 'archivum:theme';

function readTheme(): Theme {
  if (typeof window === 'undefined') return 'dark';
  return window.localStorage?.getItem(THEME_KEY) === 'light' ? 'light' : 'dark';
}

export function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage?.setItem(THEME_KEY, theme);
  } catch {
    // Private browsing modes reject writes; the in-memory theme still applies.
  }
}

type Action =
  | { type: 'SET_PAGES'; pages: Page[] }
  | { type: 'UPSERT_PAGE'; page: Page }
  | { type: 'DELETE_PAGE'; slug: string }
  | { type: 'SET_CURRENT_SLUG'; slug: string | null }
  | { type: 'SET_SAVE_STATUS'; status: SaveStatus }
  | { type: 'SET_ACTIVE_VIEW'; view: ActiveView }
  | { type: 'SET_QUICK_SEARCH_OPEN'; open: boolean }
  | { type: 'TOGGLE_LEFT' }
  | { type: 'TOGGLE_RIGHT' }
  | { type: 'SET_AUTH'; value: boolean }
  | { type: 'TOGGLE_THEME' };

const initialState: AppState = {
  pages: [],
  pagesLoaded: false,
  currentSlug: null,
  saveStatus: 'idle',
  activeView: 'library',
  quickSearchOpen: false,
  leftOpen: true,
  rightOpen: true,
  isAuthenticated: false,
  theme: readTheme(),
};

function reducer(state: AppState = initialState, action: Action): AppState {
  switch (action.type) {
    case 'SET_PAGES':
      return { ...state, pages: action.pages, pagesLoaded: true };
    case 'UPSERT_PAGE': {
      const exists = state.pages.some((p) => p.slug === action.page.slug);
      const pages = exists
        ? state.pages.map((p) => (p.slug === action.page.slug ? action.page : p))
        : [action.page, ...state.pages];
      return { ...state, pages };
    }
    case 'DELETE_PAGE':
      return { ...state, pages: state.pages.filter((p) => p.slug !== action.slug) };
    case 'SET_CURRENT_SLUG':
      return { ...state, currentSlug: action.slug };
    case 'SET_SAVE_STATUS':
      return { ...state, saveStatus: action.status };
    case 'SET_ACTIVE_VIEW':
      return { ...state, activeView: action.view };
    case 'SET_QUICK_SEARCH_OPEN':
      return { ...state, quickSearchOpen: action.open };
    case 'TOGGLE_LEFT':
      return { ...state, leftOpen: !state.leftOpen };
    case 'TOGGLE_RIGHT':
      return { ...state, rightOpen: !state.rightOpen };
    case 'TOGGLE_THEME': {
      const theme: Theme = state.theme === 'dark' ? 'light' : 'dark';
      applyTheme(theme);
      return { ...state, theme };
    }
    case 'SET_AUTH':
      return { ...state, isAuthenticated: action.value };
    default:
      return state;
  }
}

interface AppContextValue {
  state: AppState;
  dispatch: React.Dispatch<Action>;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return React.createElement(AppContext.Provider, { value: { state, dispatch } }, children);
}

export function useAppState(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppState must be used within AppProvider');
  return ctx.state;
}

export function useAppDispatch(): React.Dispatch<Action> {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppDispatch must be used within AppProvider');
  return ctx.dispatch;
}

export { reducer };
