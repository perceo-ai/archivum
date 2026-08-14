import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { AppProvider, useAppState, useAppDispatch } from './store';
import { ToastProvider } from './components/ui/Toast';
import Layout from './components/Layout';
import WikiPage from './pages/WikiPage';
import LoginPage from './pages/LoginPage';
import NotFoundPage from './pages/NotFoundPage';
import SharePage from './pages/SharePage';
import PublicWikiPage from './pages/PublicWikiPage';
import HomePage from './pages/HomePage';
import LensPage from './pages/LensPage';
import LibraryPage from './pages/LibraryPage';
import ReviewPage from './pages/ReviewPage';
import WorkflowsPage from './pages/WorkflowsPage';
import ToolsPage from './pages/ToolsPage';
import { listPages, refreshSession } from './api';

function ProtectedRoutes() {
  const { isAuthenticated, pagesLoaded } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

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
        <Layout>
          <HomePage />
        </Layout>
      } />
      <Route path="/library" element={
        <Layout>
          <LibraryPage />
        </Layout>
      } />
      <Route path="/review" element={
        <Layout>
          <ReviewPage />
        </Layout>
      } />
      <Route path="/topics" element={
        <Layout>
          <LensPage lens="topics" />
        </Layout>
      } />
      <Route path="/people" element={
        <Layout>
          <LensPage lens="people" />
        </Layout>
      } />
      <Route path="/repos" element={
        <Layout>
          <LensPage lens="repos" />
        </Layout>
      } />
      <Route path="/sources" element={
        <Layout>
          <LensPage lens="sources" />
        </Layout>
      } />
      <Route path="/wiki/*" element={
        <Layout>
          <WikiPage />
        </Layout>
      } />
      <Route path="/workflows/*" element={
        <Layout>
          <WorkflowsPage />
        </Layout>
      } />
      <Route path="/tools/*" element={
        <Layout>
          <ToolsPage />
        </Layout>
      } />
      <Route path="/graph" element={<Navigate to="/tools/graph" replace />} />
      <Route path="/query" element={<Navigate to="/tools/query" replace />} />
      <Route path="/ingest" element={<Navigate to="/tools/ingest" replace />} />
      <Route path="/search" element={<Navigate to="/library" replace />} />
      <Route path="/lint" element={<Navigate to="/tools/lint" replace />} />
      <Route path="/daily" element={<Navigate to="/workflows/daily" replace />} />
      <Route path="/projects" element={<Navigate to="/workflows/projects" replace />} />
      <Route path="/tasks" element={<Navigate to="/workflows/tasks" replace />} />
      <Route path="/decisions" element={<Navigate to="/workflows/decisions" replace />} />
      <Route path="/activity" element={<Navigate to="/workflows/activity" replace />} />
      <Route path="/settings" element={<Navigate to="/tools/settings" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

function AppRoutes() {
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
