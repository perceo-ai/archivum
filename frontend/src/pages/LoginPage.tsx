import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch } from '../store';
import { login, listPages } from '../api';

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
    <div className="h-full flex items-center justify-center" style={{ backgroundColor: '#1e1e2e' }}>
      <div
        className="w-full max-w-sm rounded-lg border p-6"
        style={{ borderColor: '#3a3a4a', backgroundColor: '#252535' }}
      >
        <h1 className="text-lg font-semibold text-text-primary mb-1">Archivum</h1>
        <p className="text-sm text-text-muted mb-4">Enter your owner password.</p>

        {error && (
          <div
            className="rounded p-3 mb-4 text-sm text-red-400 border border-red-400/30"
            style={{ backgroundColor: '#2a1a1a' }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Owner password"
            autoFocus
            className="w-full bg-transparent border rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/50"
            style={{ borderColor: '#3a3a4a' }}
          />
          <button
            type="submit"
            disabled={loading || !password.trim()}
            className="w-full px-4 py-2 rounded text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ backgroundColor: '#4B91F1', color: '#ffffff' }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="text-xs text-text-muted mt-4">
          Set <code className="px-1 py-0.5 rounded" style={{ background: '#2a2a3a' }}>OWNER_PASSWORD</code> in <code className="px-1 py-0.5 rounded" style={{ background: '#2a2a3a' }}>.env</code>.
        </p>
      </div>
    </div>
  );
}

