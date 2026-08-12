import { FormEvent, useCallback, useEffect, useState } from 'react';
import { createLifeTask, listLifeTasks } from '../api';
import type { LifeTask } from '../types';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';

export default function TasksPage() {
  const [tasks, setTasks] = useState<LifeTask[]>([]);
  const [title, setTitle] = useState('');
  const [projectKey, setProjectKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTasks(await listLifeTasks('open'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tasks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const task = await createLifeTask({
        title: title.trim(),
        ...(projectKey.trim() ? { project_key: projectKey.trim() } : {}),
      });
      setTasks((prev) => [task, ...prev]);
      setTitle('');
      setProjectKey('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create task');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="w-full flex-1 overflow-y-auto p-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-white">Tasks</h1>
        <Button onClick={refresh} variant="outline" size="sm" disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </Button>
      </div>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-[1fr_180px_auto] gap-2 mb-6">
        <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Capture a task" />
        <Input value={projectKey} onChange={(event) => setProjectKey(event.target.value)} placeholder="Project key" />
        <Button type="submit" disabled={saving || !title.trim()}>
          {saving ? 'Adding...' : 'Add'}
        </Button>
      </form>

      {error && <p className="text-sm text-destructive mb-4">{error}</p>}

      <div className="soft-border divide-y divide-white/[0.06] rounded-[8px] border bg-white/[0.035]">
        {tasks.map((task) => (
          <div key={task.id} className="flex items-start justify-between gap-3 p-3">
            <div className="min-w-0">
              <p className="text-sm text-white">{task.title}</p>
              <div className="flex items-center gap-2 mt-1">
                {task.project_key && <code className="text-xs text-text-secondary">{task.project_key}</code>}
                {task.due_date && <span className="text-xs text-text-secondary">{task.due_date}</span>}
              </div>
            </div>
            <Badge variant="secondary">{task.status}</Badge>
          </div>
        ))}
      </div>

      {!loading && tasks.length === 0 && (
        <div className="text-center py-12 text-text-secondary text-sm">No open tasks.</div>
      )}
    </div>
  );
}
