import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { AppProvider, useAppState, useAppDispatch } from './store';
import Layout from './components/Layout';
import WikiPage from './pages/WikiPage';
import LoginPage from './pages/LoginPage';
import NotFoundPage from './pages/NotFoundPage';
import GraphView from './components/GraphView';
import QueryPanel from './components/QueryPanel';
import IngestPanel from './components/IngestPanel';
import SearchBar from './components/SearchBar';
import { listPages } from './api';

function ProtectedRoutes() {
  const { isAuthenticated, pages, pagesLoaded } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  useLocation();

  useEffect(() => {
    listPages()
      .then((pages) => {
        dispatch({ type: 'SET_AUTH', value: true });
        dispatch({ type: 'SET_PAGES', pages });
      })
      .catch(() => {
        dispatch({ type: 'SET_AUTH', value: false });
        navigate('/login', { replace: true });
      });
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
      <Route path="/wiki/:slug" element={
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
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

function AppRoutes() {
  useLocation();
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={<ProtectedRoutes />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppProvider>
  );
}
