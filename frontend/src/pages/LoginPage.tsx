import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch } from '../store';
import { login, listPages } from '../api';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';

export default function LoginPage() {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
          <CardTitle>Archivum</CardTitle>
          <CardDescription>Enter your owner password.</CardDescription>
        </CardHeader>
        <CardContent>

        {error && (
          <div className="rounded-lg p-3 mb-4 text-sm text-red-300 border border-red-400/25 bg-red-500/10">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Owner password"
            autoFocus
          />
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
          Set <code className="px-1 py-0.5 rounded bg-muted/60 border border-border/50">OWNER_PASSWORD</code> in{' '}
          <code className="px-1 py-0.5 rounded bg-muted/60 border border-border/50">.env</code>.
        </p>
        </CardContent>
      </Card>
    </div>
  );
}

