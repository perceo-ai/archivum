import { useLocation, useNavigate } from 'react-router-dom';
import { cn } from '../lib/cn';
import ActivityPage from './ActivityPage';
import DailyPage from './DailyPage';
import DecisionsPage from './DecisionsPage';
import ProjectsPage from './ProjectsPage';
import TasksPage from './TasksPage';

const ITEMS = [
  { slug: 'daily', label: 'Daily', render: () => <DailyPage /> },
  { slug: 'projects', label: 'Projects', render: () => <ProjectsPage /> },
  { slug: 'tasks', label: 'Tasks', render: () => <TasksPage /> },
  { slug: 'decisions', label: 'Decisions', render: () => <DecisionsPage /> },
  { slug: 'activity', label: 'Activity', render: () => <ActivityPage /> },
];

export default function WorkflowsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const current = ITEMS.find((item) => location.pathname.endsWith(`/${item.slug}`)) ?? ITEMS[0];

  return (
    <div className="page-frame bg-transparent">
      <div className="page-header">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Workflows
        </p>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="text-3xl font-semibold tracking-tight text-foreground">Planning and execution, in one place.</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Daily notes, projects, tasks, decisions, and activity live inside one calmer workflow studio instead of five separate tabs.
            </p>
          </div>
          <div className="section-tabs">
            {ITEMS.map((item) => (
              <button
                key={item.slug}
                type="button"
                className={cn('section-tab', current.slug === item.slug && 'section-tab-active')}
                onClick={() => navigate(`/workflows/${item.slug}`)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden border border-white/10 bg-[#171616]/70">
        {current.render()}
      </div>
    </div>
  );
}
