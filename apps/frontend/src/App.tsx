import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { AppProvider, useAppState, useAppDispatch } from './store';
import { ToastProvider } from './components/ui/Toast';
import Layout from './components/Layout';
import WikiPage from './pages/WikiPage';
import LoginPage from './pages/LoginPage';
import NotFoundPage from './pages/NotFoundPage';
import SharePage from './pages/SharePage';
import PublicWikiPage from './pages/PublicWikiPage';
import SettingsPage from './pages/SettingsPage';
import LintPage from './pages/LintPage';
import DailyPage from './pages/DailyPage';
import ProjectsPage from './pages/ProjectsPage';
import TasksPage from './pages/TasksPage';
import DecisionsPage from './pages/DecisionsPage';
import ActivityPage from './pages/ActivityPage';
import GraphView from './components/GraphView';
import QueryPanel from './components/QueryPanel';
import IngestPanel from './components/IngestPanel';
import SearchBar from './components/SearchBar';
import { listPages, refreshSession } from './api';

function ProtectedRoutes() {
  const { isAuthenticated, pages, pagesLoaded } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  useLocation();

  useEffect(() => {
    async function loadPages() {
      try {
        const pages = await listPages();
        dispatch({ type: 'SET_AUTH', value: true });
        dispatch({ type: 'SET_PAGES', pages });
      } catch {
        try {
          await refreshSession();
          const pages = await listPages();
          dispatch({ type: 'SET_AUTH', value: true });
          dispatch({ type: 'SET_PAGES', pages });
        } catch {
          dispatch({ type: 'SET_AUTH', value: false });
          navigate('/login', { replace: true });
        }
      }
    }

    loadPages();
  }, [dispatch, navigate]);

  if (!pagesLoaded && !isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-text-secondary text-sm">Loading...</div>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={
        pages.length > 0
          ? <Navigate to={`/wiki/${pages[0].slug}`} replace />
          : <Navigate to="/ingest" replace />
      } />
      <Route path="/wiki/*" element={
        <Layout>
          <WikiPage />
        </Layout>
      } />
      <Route path="/graph" element={
        <Layout>
          <GraphView onNavigate={(slug) => navigate(`/wiki/${slug}`)} />
        </Layout>
      } />
      <Route path="/query" element={
        <Layout>
          <QueryPanel />
        </Layout>
      } />
      <Route path="/ingest" element={
        <Layout>
          <IngestPanel />
        </Layout>
      } />
      <Route path="/search" element={
        <Layout>
          <SearchBar />
        </Layout>
      } />
      <Route path="/lint" element={
        <Layout>
          <LintPage />
        </Layout>
      } />
      <Route path="/daily" element={
        <Layout>
          <DailyPage />
        </Layout>
      } />
      <Route path="/projects" element={
        <Layout>
          <ProjectsPage />
        </Layout>
      } />
      <Route path="/tasks" element={
        <Layout>
          <TasksPage />
        </Layout>
      } />
      <Route path="/decisions" element={
        <Layout>
          <DecisionsPage />
        </Layout>
      } />
      <Route path="/activity" element={
        <Layout>
          <ActivityPage />
        </Layout>
      } />
      <Route path="/settings" element={
        <Layout>
          <SettingsPage />
        </Layout>
      } />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

function AppRoutes() {
  useLocation();
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/share/:token" element={<SharePage />} />
      <Route path="/public" element={<PublicWikiPage />} />
      <Route path="/public/wiki/*" element={<PublicWikiPage />} />
      <Route path="/*" element={<ProtectedRoutes />} />
    </Routes>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AppProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AppProvider>
    </ToastProvider>
  );
}
