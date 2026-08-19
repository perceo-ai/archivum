import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch } from '../store';
import { login, listPages, refreshSession } from '../api';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { BrandMark } from '../shell/BrandMark';

export default function LoginPage() {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      try {
        await refreshSession();
        const pages = await listPages();
        if (cancelled) return;
        dispatch({ type: 'SET_AUTH', value: true });
        dispatch({ type: 'SET_PAGES', pages });
        navigate('/', { replace: true });
      } catch {
        if (!cancelled) {
          dispatch({ type: 'SET_AUTH', value: false });
        }
      }
    }

    restoreSession();

    return () => {
      cancelled = true;
    };
  }, [dispatch, navigate]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!password.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      await login(password.trim());
      const pages = await listPages();
      dispatch({ type: 'SET_AUTH', value: true });
      dispatch({ type: 'SET_PAGES', pages });
      navigate('/', { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="h-full flex items-center justify-center bg-bg">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="flex items-center gap-2.5">
            <BrandMark size={28} />
            <CardTitle>Archivum</CardTitle>
          </div>
          <CardDescription>Enter your owner password.</CardDescription>
        </CardHeader>
        <CardContent>

        {error && (
          <div className="rounded-lg p-3 mb-4 text-sm text-red-300 border border-red-400/25 bg-red-500/10">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <label className="block space-y-1">
            <span className="text-xs font-medium text-text-secondary">Owner password</span>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              autoFocus
            />
          </label>
          <Button
            type="submit"
            variant="primary"
            disabled={loading || !password.trim()}
            className="w-full"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <p className="text-xs text-muted-foreground mt-4">
          Use the owner password configured for this vault.
        </p>
        </CardContent>
      </Card>
    </div>
  );
}
