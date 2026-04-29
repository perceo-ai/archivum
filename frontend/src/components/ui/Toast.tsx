import * as React from 'react';
import { cn } from '../../lib/cn';

export type ToastKind = 'info' | 'success' | 'error';

export type ToastItem = {
  id: string;
  kind: ToastKind;
  title: string;
  description?: string;
};

type ToastContextValue = {
  push: (t: Omit<ToastItem, 'id'> & { id?: string }) => void;
};

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);

  const push = React.useCallback((t: Omit<ToastItem, 'id'> & { id?: string }) => {
    const id = t.id ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const item: ToastItem = { id, kind: t.kind, title: t.title, description: t.description };
    setItems((prev) => [item, ...prev].slice(0, 4));
    window.setTimeout(() => {
      setItems((prev) => prev.filter((x) => x.id !== id));
    }, 3200);
  }, []);

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="fixed right-4 top-4 z-[60] space-y-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              'w-[320px] rounded-xl border bg-panel/80 shadow-lg shadow-black/40',
              'backdrop-blur supports-[backdrop-filter]:bg-panel/60',
              'px-3 py-2',
              t.kind === 'info' && 'border-border/70',
              t.kind === 'success' && 'border-emerald-400/25',
              t.kind === 'error' && 'border-danger/25',
            )}
          >
            <div className="flex items-start gap-2">
              <KindDot kind={t.kind} />
              <div className="min-w-0">
                <div className="text-sm font-medium text-foreground truncate">{t.title}</div>
                {t.description && (
                  <div className="text-sm text-muted-foreground mt-0.5 line-clamp-2">
                    {t.description}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

function KindDot({ kind }: { kind: ToastKind }) {
  return (
    <span
      className={cn(
        'mt-1 inline-block h-2 w-2 rounded-full shrink-0',
        kind === 'info' && 'bg-accent',
        kind === 'success' && 'bg-emerald-400',
        kind === 'error' && 'bg-danger',
      )}
    />
  );
}

