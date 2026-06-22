# Conductor Docs UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Archivum frontend so the whole app feels like `conductor.build/docs` while keeping Archivum's Linux-specific workflows and existing product features intact.

**Architecture:** Replace the current dark app shell with a docs-style shell built from shared tokens, lighter primitives, and smaller shell components. Migrate high-traffic routes first so the layout, search, wiki, and navigation all share one editorial frame, then move the remaining utility pages into the same system.

**Tech Stack:** React 18, React Router 6, TypeScript, Vite, Tailwind CSS, Vitest, Radix UI, lucide-react

---

## File Structure

### Existing files to modify

- `apps/frontend/src/index.css` - global color tokens, typography, scrollbar, CodeMirror surface, docs-style utility classes
- `apps/frontend/src/store.ts` - shell state additions for docs-style search focus and inspector visibility if needed
- `apps/frontend/src/components/Layout.tsx` - replace monolithic top-nav layout with shell composition
- `apps/frontend/src/components/FileTree.tsx` - restyle and simplify vault tree into docs-nav + vault actions
- `apps/frontend/src/components/RightSidebar.tsx` - turn into contextual inspector chrome
- `apps/frontend/src/components/SearchBar.tsx` - move search to docs-style command/content layout
- `apps/frontend/src/components/StatusBar.tsx` - quieter workstation footer/status line
- `apps/frontend/src/components/ui/Button.tsx` - quieter docs-like button variants and sizes
- `apps/frontend/src/components/ui/Input.tsx` - lighter input treatment for shell/search/forms
- `apps/frontend/src/components/ui/Card.tsx` - reduce dashboard-card feel
- `apps/frontend/src/components/ui/Badge.tsx` - quieter metadata badges
- `apps/frontend/src/components/ui/Textarea.tsx` - match docs form styling
- `apps/frontend/src/components/ui/Dialog.tsx` - lighter overlays and editorial framing
- `apps/frontend/src/components/ui/DropdownMenu.tsx` - lighter docs-style menus
- `apps/frontend/src/pages/WikiPage.tsx` - editorial header, metadata row, readable editor frame
- `apps/frontend/src/pages/DailyPage.tsx` - docs-style page container/header/actions
- `apps/frontend/src/pages/ProjectsPage.tsx` - list-first editorial workflow layout
- `apps/frontend/src/pages/TasksPage.tsx` - same docs shell treatment
- `apps/frontend/src/pages/DecisionsPage.tsx` - same docs shell treatment
- `apps/frontend/src/pages/ActivityPage.tsx` - same docs shell treatment
- `apps/frontend/src/pages/SettingsPage.tsx` - same docs shell treatment
- `apps/frontend/src/pages/LintPage.tsx` - same docs shell treatment
- `apps/frontend/src/pages/LoginPage.tsx` - lighter docs-adjacent auth surface
- `apps/frontend/src/life-pages.test.tsx` - existing SSR shell/page tests to extend

### New files to create

- `apps/frontend/src/components/shell/ShellHeader.tsx` - top bar with product label, top search trigger, current location, shell actions
- `apps/frontend/src/components/shell/ShellNav.tsx` - docs-style left navigation rail and grouped route links
- `apps/frontend/src/components/shell/ShellInspector.tsx` - wrapper around contextual right sidebar
- `apps/frontend/src/components/shell/PageFrame.tsx` - shared centered content frame with editorial header helpers
- `apps/frontend/src/shell.test.tsx` - SSR tests for new shell structure and route chrome

## Task 1: Build the docs-style shell skeleton

**Files:**
- Create: `apps/frontend/src/components/shell/ShellHeader.tsx`
- Create: `apps/frontend/src/components/shell/ShellNav.tsx`
- Create: `apps/frontend/src/components/shell/ShellInspector.tsx`
- Create: `apps/frontend/src/components/shell/PageFrame.tsx`
- Create: `apps/frontend/src/shell.test.tsx`
- Modify: `apps/frontend/src/components/Layout.tsx`
- Modify: `apps/frontend/src/store.ts`

- [ ] **Step 1: Write the failing shell test**

```tsx
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { AppProvider } from './store';
import Layout from './components/Layout';

describe('docs shell', () => {
  it('renders the docs-style shell chrome', () => {
    const html = renderToString(
      <StaticRouter location="/projects">
        <AppProvider>
          <Layout>
            <div>Body</div>
          </Layout>
        </AppProvider>
      </StaticRouter>,
    );

    expect(html).toContain('Search Archivum');
    expect(html).toContain('Knowledge Base');
    expect(html).toContain('Linux workspace');
    expect(html).toContain('Body');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/frontend && npm test -- --run src/shell.test.tsx`
Expected: FAIL because `src/shell.test.tsx` does not exist yet and the current shell does not render the new labels.

- [ ] **Step 3: Create the shared shell components**

```tsx
// apps/frontend/src/components/shell/ShellHeader.tsx
import { Search, PanelLeft, PanelRight } from 'lucide-react';
import { Button } from '../ui/Button';

export default function ShellHeader() {
  return (
    <header className="shell-header">
      <div className="shell-brand">
        <span className="shell-brand-mark">Archivum</span>
        <span className="shell-brand-meta">Linux workspace</span>
      </div>
      <button type="button" className="shell-search-trigger">
        <Search className="h-4 w-4" />
        <span>Search Archivum</span>
      </button>
      <div className="shell-header-actions">
        <Button variant="ghost" size="sm"><PanelLeft className="h-4 w-4" /></Button>
        <Button variant="ghost" size="sm"><PanelRight className="h-4 w-4" /></Button>
      </div>
    </header>
  );
}
```

```tsx
// apps/frontend/src/components/shell/ShellNav.tsx
const GROUPS = [
  { label: 'Knowledge Base', items: ['Wiki', 'Search', 'Graph', 'Query'] },
  { label: 'Life OS', items: ['Daily', 'Projects', 'Tasks', 'Decisions', 'Activity'] },
  { label: 'System', items: ['Ingest', 'Lint', 'Settings'] },
];
```

```tsx
// apps/frontend/src/components/shell/PageFrame.tsx
export default function PageFrame({ title, meta, actions, children }: {
  title: string;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="page-frame">
      <header className="page-frame-header">
        <div>
          <h1 className="page-frame-title">{title}</h1>
          {meta ? <div className="page-frame-meta">{meta}</div> : null}
        </div>
        {actions ? <div className="page-frame-actions">{actions}</div> : null}
      </header>
      <div className="page-frame-body">{children}</div>
    </section>
  );
}
```

- [ ] **Step 4: Refactor `Layout.tsx` to compose the shell**

```tsx
import FileTree from './FileTree';
import RightSidebar from './RightSidebar';
import StatusBar from './StatusBar';
import ShellHeader from './shell/ShellHeader';
import ShellNav from './shell/ShellNav';
import ShellInspector from './shell/ShellInspector';

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="shell-root">
      <ShellHeader />
      <div className="shell-body">
        <aside className="shell-left">
          <ShellNav />
          <FileTree />
        </aside>
        <main className="shell-main">{children}</main>
        <ShellInspector>
          <RightSidebar />
        </ShellInspector>
      </div>
      <StatusBar />
    </div>
  );
}
```

- [ ] **Step 5: Run the shell test to verify it passes**

Run: `cd apps/frontend && npm test -- --run src/shell.test.tsx`
Expected: PASS with `docs shell renders the docs-style shell chrome`

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/components/Layout.tsx \
  apps/frontend/src/components/shell/ShellHeader.tsx \
  apps/frontend/src/components/shell/ShellNav.tsx \
  apps/frontend/src/components/shell/ShellInspector.tsx \
  apps/frontend/src/components/shell/PageFrame.tsx \
  apps/frontend/src/store.ts \
  apps/frontend/src/shell.test.tsx
git commit -m "feat(frontend): add conductor-style app shell"
```

## Task 2: Replace dark tokens and heavy primitives with docs-style UI

**Files:**
- Modify: `apps/frontend/src/index.css`
- Modify: `apps/frontend/src/components/ui/Button.tsx`
- Modify: `apps/frontend/src/components/ui/Input.tsx`
- Modify: `apps/frontend/src/components/ui/Card.tsx`
- Modify: `apps/frontend/src/components/ui/Badge.tsx`
- Modify: `apps/frontend/src/components/ui/Textarea.tsx`
- Modify: `apps/frontend/src/components/ui/Dialog.tsx`
- Modify: `apps/frontend/src/components/ui/DropdownMenu.tsx`
- Modify: `apps/frontend/src/shell.test.tsx`

- [ ] **Step 1: Extend the shell test to lock the light visual system**

```tsx
it('uses docs-style visual language', () => {
  const html = renderToString(
    <StaticRouter location="/projects">
      <AppProvider>
        <Layout>
          <button className="test-button">Body</button>
        </Layout>
      </AppProvider>
    </StaticRouter>,
  );

  expect(html).toContain('shell-root');
  expect(html).toContain('shell-search-trigger');
  expect(html).not.toContain('bg-bg');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/frontend && npm test -- --run src/shell.test.tsx`
Expected: FAIL because current classes still include the old dark-shell tokens.

- [ ] **Step 3: Rewrite the global tokens in `index.css`**

```css
:root {
  --background: 48 20% 98%;
  --foreground: 210 18% 14%;
  --card: 0 0% 100%;
  --card-foreground: 210 18% 14%;
  --popover: 0 0% 100%;
  --popover-foreground: 210 18% 14%;
  --primary: 214 68% 22%;
  --primary-foreground: 0 0% 100%;
  --secondary: 210 22% 96%;
  --secondary-foreground: 210 18% 18%;
  --muted: 210 18% 95%;
  --muted-foreground: 215 12% 42%;
  --accent: 151 55% 26%;
  --accent-foreground: 0 0% 100%;
  --border: 220 16% 88%;
  --input: 220 16% 88%;
  --ring: 214 68% 22%;
  --radius: 0.5rem;
}

body {
  background:
    linear-gradient(180deg, rgba(246, 247, 244, 0.98) 0%, rgba(244, 246, 242, 1) 100%);
  color: hsl(var(--foreground));
  font-family: "Instrument Sans", "Inter", "Segoe UI", sans-serif;
}
```

```css
.shell-root { @apply flex h-screen flex-col bg-background text-foreground; }
.shell-header { @apply flex h-14 items-center gap-4 border-b border-border bg-white/80 px-4 backdrop-blur; }
.shell-left { @apply hidden w-[320px] shrink-0 border-r border-border bg-[rgba(252,252,250,0.92)] lg:flex lg:flex-col; }
.shell-main { @apply min-w-0 flex-1 overflow-y-auto; }
.page-frame { @apply mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-8; }
.page-frame-title { @apply text-3xl font-semibold tracking-[-0.02em] text-foreground; }
.page-frame-meta { @apply mt-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground; }
```

- [ ] **Step 4: Restyle the shared UI primitives**

```tsx
// Button.tsx
variant: {
  default: 'bg-primary text-primary-foreground hover:bg-primary/92',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/90',
  ghost: 'text-muted-foreground hover:bg-secondary hover:text-foreground',
  outline: 'border border-border bg-white hover:bg-secondary hover:text-foreground',
}
size: {
  default: 'h-9 px-4 text-sm',
  sm: 'h-8 px-3 text-xs',
  icon: 'h-8 w-8',
}
```

```tsx
// Input.tsx / Textarea.tsx
'flex h-9 w-full rounded-md border border-input bg-white px-3 py-2 text-sm text-foreground shadow-none'
```

```tsx
// Card.tsx / Badge.tsx / Dialog.tsx / DropdownMenu.tsx
'rounded-md border border-border bg-white text-card-foreground shadow-[0_1px_2px_rgba(15,23,42,0.04)]'
```

- [ ] **Step 5: Run the shell test to verify it passes**

Run: `cd apps/frontend && npm test -- --run src/shell.test.tsx`
Expected: PASS and the output no longer depends on the old dark-shell classes.

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/index.css \
  apps/frontend/src/components/ui/Button.tsx \
  apps/frontend/src/components/ui/Input.tsx \
  apps/frontend/src/components/ui/Card.tsx \
  apps/frontend/src/components/ui/Badge.tsx \
  apps/frontend/src/components/ui/Textarea.tsx \
  apps/frontend/src/components/ui/Dialog.tsx \
  apps/frontend/src/components/ui/DropdownMenu.tsx \
  apps/frontend/src/shell.test.tsx
git commit -m "feat(frontend): add conductor-style tokens and primitives"
```

## Task 3: Rebuild navigation, vault rail, inspector, and search behavior

**Files:**
- Modify: `apps/frontend/src/components/FileTree.tsx`
- Modify: `apps/frontend/src/components/RightSidebar.tsx`
- Modify: `apps/frontend/src/components/SearchBar.tsx`
- Modify: `apps/frontend/src/components/StatusBar.tsx`
- Modify: `apps/frontend/src/life-pages.test.tsx`

- [ ] **Step 1: Write the failing navigation/search regression tests**

```tsx
it('keeps life os links inside the docs nav shell', () => {
  const html = renderToString(
    <StaticRouter location="/daily">
      <AppProvider>
        <Layout>
          <div>Body</div>
        </Layout>
      </AppProvider>
    </StaticRouter>,
  );

  expect(html).toContain('Knowledge Base');
  expect(html).toContain('Life OS');
  expect(html).toContain('System');
});

it('renders search inside an editorial page frame', () => {
  const html = renderToString(<SearchBar />);
  expect(html).toContain('Search your vault');
  expect(html).toContain('Search results');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npm test -- --run src/life-pages.test.tsx`
Expected: FAIL because the current layout has a button row instead of grouped docs nav, and search still uses the old utility panel layout.

- [ ] **Step 3: Simplify `FileTree.tsx` into docs-nav plus calm vault actions**

```tsx
return (
  <div className="flex min-h-0 flex-1 flex-col">
    <div className="border-t border-border px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        Vault
      </div>
      <Input
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
        placeholder="Filter pages and folders"
        className="mt-3"
      />
    </div>
    <ScrollArea className="flex-1 px-2 pb-4">
      <TreeSection title="Workspace files">{renderNodes(tree.children, '')}</TreeSection>
    </ScrollArea>
  </div>
);
```

- [ ] **Step 4: Convert `SearchBar.tsx`, `RightSidebar.tsx`, and `StatusBar.tsx` to the new shell language**

```tsx
// SearchBar.tsx
return (
  <PageFrame
    title="Search"
    meta={<><span>Search your vault</span><span>Keyboard-first</span></>}
  >
    <form onSubmit={runSearch} className="flex gap-2">
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your vault" />
      <Button type="submit">{loading ? 'Searching...' : 'Run search'}</Button>
    </form>
    <section aria-label="Search results" className="mt-6 space-y-3">
      {results.map(/* existing result render */)}
    </section>
  </PageFrame>
);
```

```tsx
// RightSidebar.tsx
<div className="flex h-full flex-col">
  <div className="border-b border-border px-4 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
    Inspector
  </div>
  <div className="px-3 py-2">{/* existing tabs */}</div>
</div>
```

```tsx
// StatusBar.tsx
<footer className="flex h-8 items-center border-t border-border bg-white/70 px-4 text-[11px] text-muted-foreground">
  <span>{currentSlug ?? 'workspace idle'}</span>
  <span className="mx-2">/</span>
  <span>{text}</span>
</footer>
```

- [ ] **Step 5: Run the regression tests to verify they pass**

Run: `cd apps/frontend && npm test -- --run src/life-pages.test.tsx`
Expected: PASS with grouped docs nav labels and the new search frame copy.

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/components/FileTree.tsx \
  apps/frontend/src/components/RightSidebar.tsx \
  apps/frontend/src/components/SearchBar.tsx \
  apps/frontend/src/components/StatusBar.tsx \
  apps/frontend/src/life-pages.test.tsx
git commit -m "feat(frontend): restyle navigation and search flows"
```

## Task 4: Rewrite the wiki surface around an editorial page frame

**Files:**
- Modify: `apps/frontend/src/pages/WikiPage.tsx`
- Modify: `apps/frontend/src/components/Editor/Editor.tsx`
- Modify: `apps/frontend/src/index.css`
- Modify: `apps/frontend/src/shell.test.tsx`

- [ ] **Step 1: Write the failing wiki shell test**

```tsx
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import WikiPage from './pages/WikiPage';

it('renders wiki inside an editorial frame', () => {
  const html = renderToString(
    <MemoryRouter initialEntries={['/wiki/test-page']}>
      <Routes>
        <Route path="/wiki/*" element={<WikiPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(html).toContain('Page title');
  expect(html).toContain('Tags');
  expect(html).toContain('Save');
});
```

- [ ] **Step 2: Run the wiki shell test to verify it fails**

Run: `cd apps/frontend && npm test -- --run src/shell.test.tsx`
Expected: FAIL because the test does not exist yet and the wiki page is still using the old utility-strip framing.

- [ ] **Step 3: Replace the wiki title bar with `PageFrame`**

```tsx
return (
  <PageFrame
    title={titleDraft || page?.title || 'Untitled'}
    meta={
      <>
        <span>{slugStr}</span>
        <span>{parsedTags.length ? parsedTags.join(', ') : 'No tags'}</span>
        {page?.authored_by === 'agent' ? <Badge variant="secondary">AI draft</Badge> : null}
      </>
    }
    actions={
      <>
        <Button variant="secondary" size="sm" onClick={handleSaveNow}>Save</Button>
        <PageMenu /* existing props */ />
      </>
    }
  >
    <div className="grid gap-4">
      <div className="grid gap-3 md:grid-cols-[1fr_280px]">
        <Input aria-label="Page title" value={titleDraft} onChange={/* existing handler */} />
        <Input aria-label="Tags" value={tagsDraft} onChange={/* existing handler */} />
      </div>
      <div className="editor-frame">{page ? <Editor /* existing props */ /> : loadingSkeleton}</div>
    </div>
  </PageFrame>
);
```

- [ ] **Step 4: Lighten the editor surface in `Editor.tsx` and `index.css`**

```css
.editor-frame {
  @apply overflow-hidden rounded-md border border-border bg-white;
}

.cm-editor {
  background: white;
  color: hsl(var(--foreground));
}

.cm-scroller {
  font-family: "IBM Plex Mono", "JetBrains Mono", monospace !important;
  line-height: 1.7 !important;
}
```

- [ ] **Step 5: Run the wiki shell test to verify it passes**

Run: `cd apps/frontend && npm test -- --run src/shell.test.tsx`
Expected: PASS with the editorial wiki frame and lighter editor surface.

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/pages/WikiPage.tsx \
  apps/frontend/src/components/Editor/Editor.tsx \
  apps/frontend/src/index.css \
  apps/frontend/src/shell.test.tsx
git commit -m "feat(frontend): restyle wiki editing surface"
```

## Task 5: Move the Life OS and utility pages into the same docs frame

**Files:**
- Modify: `apps/frontend/src/pages/DailyPage.tsx`
- Modify: `apps/frontend/src/pages/ProjectsPage.tsx`
- Modify: `apps/frontend/src/pages/TasksPage.tsx`
- Modify: `apps/frontend/src/pages/DecisionsPage.tsx`
- Modify: `apps/frontend/src/pages/ActivityPage.tsx`
- Modify: `apps/frontend/src/pages/SettingsPage.tsx`
- Modify: `apps/frontend/src/pages/LintPage.tsx`
- Modify: `apps/frontend/src/pages/LoginPage.tsx`
- Modify: `apps/frontend/src/life-pages.test.tsx`

- [ ] **Step 1: Expand the route tests to lock the new page framing**

```tsx
it('renders the daily note workflow inside the page frame', () => {
  const html = renderToString(
    <StaticRouter location="/daily">
      <DailyPage />
    </StaticRouter>,
  );

  expect(html).toContain('Open daily note');
  expect(html).toContain('page-frame');
});

it('renders the projects workflow as an editorial list page', () => {
  const html = renderToString(
    <StaticRouter location="/projects">
      <ProjectsPage />
    </StaticRouter>,
  );

  expect(html).toContain('Projects');
  expect(html).toContain('Create project');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npm test -- --run src/life-pages.test.tsx`
Expected: FAIL because the pages currently use bespoke full-width wrappers and inconsistent controls.

- [ ] **Step 3: Convert each page to use `PageFrame`**

```tsx
// DailyPage.tsx
return (
  <PageFrame
    title="Daily"
    meta={<><span>Open or create a daily note</span><span>workspace journal</span></>}
  >
    <div className="flex flex-wrap items-center gap-3">
      <Input type="date" value={date} onChange={(event) => setDate(event.target.value)} className="max-w-48" />
      <Button onClick={openDaily}>{loading ? 'Opening...' : 'Open daily note'}</Button>
    </div>
  </PageFrame>
);
```

```tsx
// ProjectsPage.tsx
return (
  <PageFrame
    title="Projects"
    meta={<><span>Project memory and current work</span><span>{projects.length} tracked</span></>}
    actions={<Button onClick={refresh} variant="secondary" size="sm">{loading ? 'Loading...' : 'Refresh'}</Button>}
  >
    <form className="grid gap-3">{/* existing form, relaid out */}</form>
    <div className="divide-y divide-border rounded-md border border-border bg-white">
      {projects.map(/* existing project rows rendered as list rows */)}
    </div>
  </PageFrame>
);
```

```tsx
// Apply the same structure to TasksPage, DecisionsPage, ActivityPage, SettingsPage, LintPage, LoginPage.
// Keep existing data flow, replace only shell/layout/card heaviness.
```

- [ ] **Step 4: Run the route tests to verify they pass**

Run: `cd apps/frontend && npm test -- --run src/life-pages.test.tsx`
Expected: PASS with docs-style page frames on the Life OS routes.

- [ ] **Step 5: Run a frontend build check**

Run: `cd apps/frontend && npm run build`
Expected: PASS with Vite and TypeScript finishing successfully.

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/pages/DailyPage.tsx \
  apps/frontend/src/pages/ProjectsPage.tsx \
  apps/frontend/src/pages/TasksPage.tsx \
  apps/frontend/src/pages/DecisionsPage.tsx \
  apps/frontend/src/pages/ActivityPage.tsx \
  apps/frontend/src/pages/SettingsPage.tsx \
  apps/frontend/src/pages/LintPage.tsx \
  apps/frontend/src/pages/LoginPage.tsx \
  apps/frontend/src/life-pages.test.tsx
git commit -m "feat(frontend): align life os and utility pages with docs shell"
```

## Task 6: Verify the redesign against the reference and finish

**Files:**
- Modify: `docs/project/progress.md`
- Modify: `Progress.md`

- [ ] **Step 1: Run the frontend test suite**

Run: `cd apps/frontend && npm test`
Expected: PASS for `src/api.test.ts`, `src/life-pages.test.tsx`, `src/shell.test.tsx`, and any other frontend tests.

- [ ] **Step 2: Run the production build again**

Run: `cd apps/frontend && npm run build`
Expected: PASS with no TypeScript or Vite errors.

- [ ] **Step 3: Manually verify the reference fit**

Run:

```bash
cat <<'EOF'
Check in browser:
1. Open /wiki/<slug>, /search, /projects, /daily, /settings
2. Compare shell, spacing, search placement, nav grouping, borders, typography rhythm against conductor.build/docs
3. Confirm Linux flavor still shows up in workspace/session/path metadata
4. Confirm no dark-shell leftovers remain
EOF
```

Expected: Manual checklist printed, then completed in browser by the implementer.

- [ ] **Step 4: Update the progress docs**

```md
| Conductor-style frontend rewrite | ✅ Done | Docs-style shell, editorial page frames, Linux-flavored chrome across all major routes |
```

- [ ] **Step 5: Commit**

```bash
git add docs/project/progress.md Progress.md
git commit -m "docs: record conductor-style frontend rewrite"
```

## Self-Review

### Spec coverage

- Product frame: covered by Task 1 and Task 2
- Interaction model: covered by Task 1, Task 3, and Task 4
- Visual system: covered by Task 2
- Route-by-route rewrite: covered by Task 4 and Task 5
- Verification bar: covered by Task 6

### Placeholder scan

- No `TODO`, `TBD`, or "implement later" placeholders remain.
- Commands, file paths, and target files are explicit.
- Test commands and expected outcomes are present for each task.

### Type consistency

- Shared shell helpers are introduced once in Task 1 and reused consistently afterward.
- `PageFrame` is the shared route wrapper referenced in Tasks 3, 4, and 5.
- The plan preserves existing data APIs and route names instead of inventing new backend contracts.

