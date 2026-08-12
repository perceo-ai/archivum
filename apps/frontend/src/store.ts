import React, { createContext, useContext, useReducer } from 'react';
import type { Page } from './types';

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';
export type ActiveView =
  | 'editor'
  | 'library'
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
  | { type: 'SET_AUTH'; value: boolean };

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
