import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ensureDailyNote } from '../api';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';

export default function DailyPage() {
  const navigate = useNavigate();
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openDaily() {
    setLoading(true);
    setError(null);
    try {
      const page = await ensureDailyNote(date);
      navigate(`/wiki/${page.slug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open daily note');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 max-w-3xl mx-auto w-full">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-text-primary">Daily</h1>
      </div>
      <div className="flex items-center gap-2">
        <Input
          value={date}
          onChange={(event) => setDate(event.target.value)}
          type="date"
          className="max-w-48"
        />
        <Button onClick={openDaily} disabled={loading}>
          {loading ? 'Opening...' : 'Open daily note'}
        </Button>
      </div>
      {error && <p className="text-sm text-destructive mt-3">{error}</p>}
    </div>
  );
}
