import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createLifeProject, listLifeProjects } from '../api';
import type { LifeProject } from '../types';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Textarea } from '../components/ui/Textarea';
import { Badge } from '../components/ui/Badge';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<LifeProject[]>([]);
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [summary, setSummary] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setProjects(await listLifeProjects());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load projects');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!key.trim() || !name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const project = await createLifeProject({
        key: key.trim(),
        name: name.trim(),
        summary: summary.trim(),
      });
      setProjects((prev) => [project, ...prev.filter((p) => p.key !== project.key)]);
      setKey('');
      setName('');
      setSummary('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="w-full flex-1 overflow-y-auto p-4">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-white">Projects</h1>
        <Button onClick={refresh} variant="outline" size="sm" disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </Button>
      </div>

      <form onSubmit={handleSubmit} className="grid gap-2 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-[160px_1fr_auto] gap-2">
          <Input value={key} onChange={(event) => setKey(event.target.value)} placeholder="project-key" />
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Project name" />
          <Button type="submit" disabled={saving || !key.trim() || !name.trim()}>
            {saving ? 'Creating...' : 'Create'}
          </Button>
        </div>
        <Textarea
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          placeholder="Summary"
          rows={3}
        />
      </form>

      {error && <p className="text-sm text-destructive mb-4">{error}</p>}

      <div className="space-y-3">
        {projects.map((project) => (
          <button
            type="button"
            key={project.key}
            className="soft-border block w-full rounded-[8px] border bg-white/[0.045] p-5 text-left text-white transition-colors hover:border-primary/50 disabled:cursor-default disabled:hover:border-white/[0.06]"
            onClick={() => project.page_slug && navigate(`/wiki/${project.page_slug}`)}
            disabled={!project.page_slug}
          >
            <span className="flex items-start justify-between gap-3">
              <span className="text-base font-semibold leading-none tracking-tight text-white">
                {project.name}
              </span>
              <Badge variant="secondary">{project.status}</Badge>
            </span>
            <span className="block text-sm text-text-secondary mt-3">{project.summary || project.key}</span>
          </button>
        ))}
      </div>

      {!loading && projects.length === 0 && (
        <div className="text-center py-12 text-muted-foreground text-sm">
          No projects yet. Create one when a body of work needs its own notes and tasks.
        </div>
      )}
    </div>
  );
}
