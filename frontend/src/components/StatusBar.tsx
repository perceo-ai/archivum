import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppState, useAppDispatch } from '../store';
import { logout } from '../api';
import { Button } from './ui/Button';

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
      className="h-9 shrink-0 border-t border-border px-3 flex items-center text-xs bg-panel/30 backdrop-blur supports-[backdrop-filter]:bg-panel/20"
    >
      <span className="text-muted-foreground">{currentSlug ? currentSlug : '—'}</span>
      <span className="mx-2 text-muted-foreground">·</span>
      <span
        className={
          saveStatus === 'error'
            ? 'text-red-400'
            : saveStatus === 'saving'
              ? 'text-accent'
              : 'text-muted-foreground'
        }
      >
        {text}
      </span>
      <div className="flex-1" />
      <Button variant="ghost" size="sm" onClick={handleLogout}>
        Logout
      </Button>
    </footer>
  );
}

