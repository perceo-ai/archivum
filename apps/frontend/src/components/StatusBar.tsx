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
      className="subtle-divider flex h-10 shrink-0 items-center border-t bg-background/70 px-4 text-xs backdrop-blur md:px-6"
    >
      <span className="font-mono text-muted-foreground">{currentSlug ? currentSlug : 'library/root'}</span>
      <span className="mx-2 text-muted-foreground">·</span>
      <span
        className={
          saveStatus === 'error'
            ? 'text-destructive'
            : saveStatus === 'saving'
              ? 'text-primary'
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
