import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppState, useAppDispatch } from '../store';
import { logout } from '../api';

export default function StatusBar() {
  const { saveStatus, currentSlug } = useAppState();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const text = useMemo(() => {
    switch (saveStatus) {
      case 'saving':
        return 'Saving…';
      case 'saved':
        return 'Saved';
      case 'error':
        return 'Save failed';
      default:
        return 'Ready';
    }
  }, [saveStatus]);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      dispatch({ type: 'SET_AUTH', value: false });
      navigate('/login', { replace: true });
    }
  }

  return (
    <footer
      className="h-8 shrink-0 border-t px-3 flex items-center text-xs"
      style={{ borderColor: '#3a3a4a', backgroundColor: '#1a1a2a' }}
    >
      <span className="text-text-muted">{currentSlug ? currentSlug : '—'}</span>
      <span className="mx-2 text-text-muted">·</span>
      <span
        className={
          saveStatus === 'error'
            ? 'text-red-400'
            : saveStatus === 'saving'
              ? 'text-accent'
              : 'text-text-secondary'
        }
      >
        {text}
      </span>
      <div className="flex-1" />
      <button
        onClick={handleLogout}
        className="text-text-muted hover:text-text-secondary transition-colors"
      >
        Logout
      </button>
    </footer>
  );
}

