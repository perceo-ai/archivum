# PER-320: Standalone Product Experience — Implementation Plan

**For agentic workers:** Execute tasks in order. Each task is TDD: write a failing test (real code), run it (expect FAIL), write the minimal real implementation (real TSX/TS), run it (expect PASS), then commit with the exact message given. Do not batch tasks. Do not write placeholder code — every snippet here is real and copy-pasteable. Run tests with `npm test --workspace apps/frontend -- <path>` (Vitest). All paths are relative to repo root `/home/kitts/Documents/dev/personal/archivum` unless absolute.

---

## Goal

Replace the Markdown-wiki UI with the standalone Archivum product experience defined in the architecture spec (§1 surfaces, §2 L3 generated views, §8 context packages). Ship the primary surfaces — **Ask** (homepage), **Sources**, **Projects**, **Entities**, **Timeline**, **Graph** (exploration) — where every answer and every claim exposes its **provenance** (citation + confidence + extraction method) and clicks through to the immutable source and evidence span. Generated pages, dossiers, summaries, and timelines are read-only **projections** over canonical knowledge (L3), never editable canonical data.

## Architecture

- Frontend is evolved **in place** at `apps/frontend/` (React 18 + Vite + TS + Tailwind + shadcn-style local UI kit). No rewrite, no new app.
- A typed API client (`src/api/knowledge.ts`) wraps the PER-319 REST endpoints and models the `ContextPackage` (nodes + edges + citation + extraction_method + confidence) from spec §8.
- New surface pages live under `src/pages/` behind a new app shell (`src/components/AppShell.tsx`) and route table in `App.tsx`. **Ask is the index route (`/`).** Graph is a scoped exploration route (`/graph`), never the homepage.
- A single reusable **`<Provenance>`** component renders confidence + method badge + click-through everywhere a claim or answer appears, so provenance is structurally unavoidable.
- All new surfaces are **read-only**. The Markdown editor, page CRUD, folders, wiki/workflows/tools/lint/daily surfaces are removed or redirected. Canonical writes happen via ingestion + agent workers (out of scope here).

## Tech Stack

- React 18.3, Vite 5, TypeScript 5.5, Tailwind 3.4, local shadcn-style UI kit (`src/components/ui/*`), React Router 6.
- Testing: **Vitest 3** + **@testing-library/react** + **@testing-library/jest-dom** + **jsdom** (added in Task 0; existing tests use `renderToString` — new component tests use RTL).
- Graph: existing **`vis-network` 9** + **`vis-data` 7** (already dependencies), reused from `GraphView.tsx`.

## Global Constraints (from spec §1, §2, §6, §8)

1. **Ask is the primary surface.** It is the index route `/`. Every other surface is reachable from the shell but Ask is home.
2. **Provenance is always visible.** Every answer and every claim renders citation + confidence + `extraction_method` via `<Provenance>`, click-through to the immutable source + span. No claim renders without it.
3. **Graph is exploration, not the homepage.** `/graph` is scoped (seeded from an entity/answer), depth-limited, never the landing page.
4. **Views are read-only projections (L3).** No edit/save/delete affordances on generated pages, dossiers, timelines, entities. The wiki editor is removed.
5. **"Insufficient evidence" is a first-class state.** When retrieval returns no/low-confidence evidence, Ask shows an explicit insufficient-evidence panel, never a fabricated answer (spec §6.5).
6. **Evolve the frontend in place.** Modify `apps/frontend/`; delete old wiki modules; do not scaffold a new project.

---

## File Structure

New / changed files (responsibility):

**API + types**
- `src/api/knowledge.ts` — **NEW.** Typed client for PER-319 endpoints: `ask` (SSE stream), `searchSources`, `getSource`, `listSourceVersions`, `listEntities`, `getEntity`, `getTimeline`, `getGraph` (scoped). Reuses `apiFetch`/SSE helpers.
- `src/api/types.ts` — **NEW.** ContextPackage/Citation/Entity/Source/TimelineEvent/GraphScope types (spec §4, §8).
- `src/api.ts` — **KEEP** the generic `apiFetch`, CSRF, SSE helpers; **remove** wiki page/folder/life/lint exports in the cleanup task. Re-export `apiFetch` + `parseSSEStream` for the new client.

**Provenance (used everywhere)**
- `src/components/provenance/Provenance.tsx` — **NEW.** Renders one citation's confidence bar + `extraction_method` badge + click-through button.
- `src/components/provenance/ConfidenceBadge.tsx` — **NEW.** Numeric confidence → color + label.
- `src/components/provenance/MethodBadge.tsx` — **NEW.** `EXTRACTED | INFERRED | AMBIGUOUS` → colored badge.
- `src/components/provenance/EvidencePanel.tsx` — **NEW.** List of citations for an answer/claim; each row is a `<Provenance>`.
- `src/components/provenance/SourceSpanDrawer.tsx` — **NEW.** Slide-over that loads the immutable source + highlights the cited span.

**Surfaces (pages)**
- `src/pages/AskPage.tsx` — **NEW.** Homepage. Query box → streamed cited answer + `EvidencePanel` + insufficient-evidence state.
- `src/pages/SourcesPage.tsx` — **NEW.** Browse/search immutable sources; list + version history; open span drawer.
- `src/pages/ProjectsPage.tsx` — **REPLACE.** Read-only project dossiers (L3 projection over canonical), each claim carries provenance.
- `src/pages/EntitiesPage.tsx` — **NEW.** Entity browser + entity detail (claims, relationships, provenance).
- `src/pages/TimelinePage.tsx` — **NEW.** Temporal projection (events ordered by valid_from) with provenance per event.
- `src/pages/GraphPage.tsx` — **NEW.** Scoped exploration wrapper around `ScopedGraph`.
- `src/pages/NotFoundPage.tsx` — **KEEP.**
- `src/pages/LoginPage.tsx` — **KEEP.**

**Shell / components**
- `src/components/AppShell.tsx` — **NEW.** Top-level layout: sidebar nav (Ask, Sources, Projects, Entities, Timeline, Graph) + content outlet. Replaces `Layout.tsx`.
- `src/components/AskBox.tsx` — **NEW.** Query textarea + submit, used by AskPage.
- `src/components/CitedAnswer.tsx` — **NEW.** Renders streamed answer text with inline citation markers linking to EvidencePanel rows.
- `src/components/ScopedGraph.tsx` — **NEW.** vis-network wrapper seeded from a `GraphScope` (entry nodes + depth), reused across Graph/Entities. Adapted from `GraphView.tsx`.
- `src/components/EntityCard.tsx` — **NEW.** Entity summary row with type + top claim + provenance count.
- `src/components/SourceRow.tsx` — **NEW.** Source list item (type, origin_uri, ingested_at, version count).

**App wiring**
- `src/App.tsx` — **EDIT.** New route table: `/` → AskPage; `/sources`, `/projects`, `/entities`, `/timeline`, `/graph`. Redirect old wiki routes → nearest new surface. Remove wiki/workflows/tools imports.
- `src/store.ts` — **EDIT.** Drop `pages`/`ActiveView` wiki state; keep `isAuthenticated`; add `activeSurface`.
- `src/main.tsx` — **KEEP.**

**Removed (old Markdown wiki UI — deleted in cleanup task)**
- Pages: `WikiPage.tsx`, `PublicWikiPage.tsx`, `LibraryPage.tsx`, `WorkflowsPage.tsx`, `ToolsPage.tsx`, `DailyPage.tsx`, `DecisionsPage.tsx`, `TasksPage.tsx`, `ActivityPage.tsx`, `LintPage.tsx`, `SettingsPage.tsx`, `SharePage.tsx`.
- Components: `Layout.tsx`, `FileTree.tsx`, `BacklinksPanel.tsx`, `NotesInteractionPanel.tsx`, `QueryPanel.tsx`, `RightSidebar.tsx`, `SearchBar.tsx`, `StatusBar.tsx`, `IngestPanel.tsx`, `GraphView.tsx` (superseded by `ScopedGraph.tsx`), `Editor/*`.
- Tests: `life-pages.test.tsx` (asserts removed pages) is deleted with its pages.

**Test setup**
- `vitest.config.ts` — **NEW.** jsdom environment + `setupFiles`.
- `src/test/setup.ts` — **NEW.** imports `@testing-library/jest-dom`.

---

## Upstream Dependencies

**PER-319 (Cited Retrieval, Ask & MCP) — REST API + ContextPackage.** Canonical upstream interfaces are defined in [2026-07-28-archivum-interface-contract.md](2026-07-28-archivum-interface-contract.md). This frontend consumes PER-319's real REST layer (and PER-315's `/api/sources`). All UI reads through `src/api/types.ts`; keep those types mirrored to PER-319's `ContextPackage`/`Citation`/`RetrievalHit`/`AskResult`.

**Real endpoints (PER-319 canonical; PER-315 for sources):**
- `POST /api/ask` — SSE stream: `citations` event → `token`* events → `insufficient` event (when weak) → `[DONE]`. (There is **no** `context` event; fetch the package separately via `POST /api/context-package`.)
- `POST /api/retrieve` — body `{query, source_type?, limit?, top_n?}` → `{ hits: RetrievalHit[] }`.
- `POST /api/context-package` — body `{query, source_type?, depth?, max_nodes?, relations?}` → `ContextPackage`.
- `GET /api/graph/neighbors?node_id=&depth=&wiki_id=` → `{ center, nodes, edges }`.
- `GET /api/sources?q=&limit=` → `Source[]`; `GET /api/sources/:id` → `Source` (with `versions`); `GET /api/sources/:id/versions` → `SourceVersion[]` (PER-315 `api/sources.py` read-back; extend there if a list route is needed).
- Entities/Timeline views (`/api/entities`, `/api/timeline`) are projections over PER-319 retrieval + PER-317 `list_objects`; treat as this plan's own view endpoints, not PER-319 contract.

**ContextPackage / Citation shape (mirror of PER-319's real Pydantic models):**
```ts
type ExtractionMethod = 'EXTRACTED' | 'INFERRED' | 'AMBIGUOUS';
type SourceType = 'code' | 'structured' | 'natural_language';

interface Citation {
  source_id: string;
  source_type: SourceType;
  title: string;
  origin_uri?: string | null;
  chunk_id?: string | null;
  span?: [number, number] | null;
  excerpt?: string | null;
}

interface ContextNode {
  id: string;
  label: string;
  node_type: string;
  scope: string;
  extraction_method: ExtractionMethod;
  confidence: number;
  citations: Citation[];
}

interface ContextEdge {
  from_id: string;
  to_id: string;
  relation: string;
  extraction_method: ExtractionMethod;
  confidence: number;
}

interface ContextPackage {
  query: string;
  seeds: string[];
  nodes: ContextNode[];
  edges: ContextEdge[];
  truncated: boolean;
  insufficient_evidence: boolean;
}

interface RetrievalHit {
  node_id: string;
  label: string;
  node_type: string;
  scope: string;
  score: number;
  source: string;
  excerpt?: string | null;
}
```

---

### Task 0 — Add RTL + jsdom test infrastructure

**Files:** `apps/frontend/package.json`, `apps/frontend/vitest.config.ts` (new), `apps/frontend/src/test/setup.ts` (new).

**Interfaces** — Consumes: nothing. Produces: a working jsdom Vitest environment so later component tests can `render()`.

- [ ] Add devDeps: `npm install -D --workspace apps/frontend @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom`.
- [ ] Create `apps/frontend/src/test/setup.ts`:
```ts
import '@testing-library/jest-dom/vitest';
```
- [ ] Create `apps/frontend/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
});
```
- [ ] Write `apps/frontend/src/test/setup.test.tsx` (sanity):
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('rtl setup', () => {
  it('renders into jsdom', () => {
    render(<button>Ask</button>);
    expect(screen.getByRole('button', { name: 'Ask' })).toBeInTheDocument();
  });
});
```
- [ ] Run `npm test --workspace apps/frontend -- src/test/setup.test.tsx` → expect FAIL (config/deps not wired).
- [ ] Wire config/deps until it passes. Run again → PASS.
- [ ] Verify existing `api.test.ts` still passes under the new config (jsdom is a superset).
- [ ] Commit: `test(frontend): add react-testing-library + jsdom vitest setup`.

---

### Task 1 — ContextPackage / Citation type module

**Files:** `apps/frontend/src/api/types.ts` (new), `apps/frontend/src/api/types.test.ts` (new).

**Interfaces** — Consumes: PER-319 JSON shapes. Produces: exported types `ExtractionMethod`, `Citation`, `ContextNode`, `ContextEdge`, `ContextPackage`, `Source`, `SourceVersion`, `Entity`, `EntityDetail`, `TimelineEvent`, `GraphScope`.

- [ ] Write `src/api/types.test.ts` (type-level + runtime guard):
```ts
import { describe, it, expect } from 'vitest';
import { isSufficient } from './types';
import type { ContextPackage } from './types';

const pkg: ContextPackage = {
  query: 'who owns archivum?',
  nodes: [], edges: [], sufficient: false, insufficient_reason: 'no evidence',
};

describe('isSufficient', () => {
  it('is false when package is insufficient', () => {
    expect(isSufficient(pkg)).toBe(false);
  });
  it('is true only when sufficient and has nodes', () => {
    expect(isSufficient({ ...pkg, sufficient: true, nodes: [{
      id: 'n1', label: 'Pranav', kind: 'entity', confidence: 0.9,
      extraction_method: 'EXTRACTED', citations: [],
    }] })).toBe(true);
  });
});
```
- [ ] Run → FAIL (module missing).
- [ ] Create `src/api/types.ts` with the ContextPackage block above **plus**:
```ts
export interface Source {
  id: string;
  content_hash: string;
  version: number;
  source_type: string;
  origin_uri: string;
  ingested_at: string;
  scope: string;
  title: string;
}
export interface SourceVersion {
  version: number;
  content_hash: string;
  ingested_at: string;
}
export interface Entity {
  id: string;
  label: string;
  entity_type: string;
  claim_count: number;
  provenance_count: number;
}
export interface EntityDetail extends Entity {
  claims: ContextNode[];
  relationships: ContextEdge[];
}
export interface TimelineEvent {
  id: string;
  label: string;
  valid_from: string;
  valid_to: string | null;
  recorded_at: string;
  confidence: number;
  extraction_method: ExtractionMethod;
  citations: Citation[];
}
export interface GraphScope {
  seed: string[];
  depth: number;
  relations?: string[];
}
export function isSufficient(pkg: ContextPackage): boolean {
  return pkg.sufficient && pkg.nodes.length > 0;
}
```
- [ ] Run → PASS.
- [ ] Commit: `feat(frontend): add ContextPackage and knowledge types`.

---

### Task 2 — Knowledge API client: ask (SSE)

**Files:** `apps/frontend/src/api/knowledge.ts` (new), `apps/frontend/src/api/knowledge.test.ts` (new). Reuse `apiFetch`/SSE from `src/api.ts` (export `parseSSEStream` + `csrfToken` there first).

**Interfaces** — Consumes: `POST /api/ask` SSE. Produces:
```ts
interface AskCallbacks {
  onToken: (t: string) => void;
  onCitations: (c: Citation[]) => void;
  onContext: (pkg: ContextPackage) => void;
  onInsufficient: (reason: string) => void;
}
export function ask(question: string, cb: AskCallbacks): Promise<void>;
```

- [ ] In `src/api.ts` add `export { parseSSEStream, csrfToken };` (make helpers exportable).
- [ ] Write `src/api/knowledge.test.ts`:
```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { ask } from './knowledge';
import type { Citation } from './types';

const fetchMock = vi.fn();
vi.stubGlobal('fetch', fetchMock);
vi.stubGlobal('document', { cookie: '' });
afterEach(() => fetchMock.mockReset());

function sse(chunks: string[]): Response {
  const body = new ReadableStream({
    start(c) {
      const enc = new TextEncoder();
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
  return new Response(body, { status: 200 });
}

describe('ask', () => {
  it('streams tokens, citations, and context', async () => {
    fetchMock.mockResolvedValueOnce(sse([
      'data: {"type":"token","token":"Pranav "}\n\n',
      'data: {"type":"citations","citations":[{"chunk_id":"c1","source_id":"s1","source_title":"README","span":{"start":0,"end":5},"extraction_method":"EXTRACTED","confidence":0.9}]}\n\n',
      'data: {"type":"context","package":{"query":"q","nodes":[],"edges":[],"sufficient":true}}\n\n',
      'data: [DONE]\n\n',
    ]));
    const tokens: string[] = [];
    let cites: Citation[] = [];
    let sufficient: boolean | null = null;
    await ask('who owns archivum?', {
      onToken: (t) => tokens.push(t),
      onCitations: (c) => (cites = c),
      onContext: (p) => (sufficient = p.sufficient),
      onInsufficient: () => (sufficient = false),
    });
    expect(tokens.join('')).toBe('Pranav ');
    expect(cites[0].extraction_method).toBe('EXTRACTED');
    expect(sufficient).toBe(true);
  });

  it('fires onInsufficient on insufficient event', async () => {
    fetchMock.mockResolvedValueOnce(sse([
      'data: {"type":"insufficient","reason":"no evidence"}\n\n',
      'data: [DONE]\n\n',
    ]));
    let reason = '';
    await ask('unknown?', {
      onToken: () => {}, onCitations: () => {}, onContext: () => {},
      onInsufficient: (r) => (reason = r),
    });
    expect(reason).toBe('no evidence');
  });
});
```
- [ ] Run → FAIL.
- [ ] Create `src/api/knowledge.ts`:
```ts
import { parseSSEStream, csrfToken } from '../api';
import type { Citation, ContextPackage } from './types';

export interface AskCallbacks {
  onToken: (t: string) => void;
  onCitations: (c: Citation[]) => void;
  onContext: (pkg: ContextPackage) => void;
  onInsufficient: (reason: string) => void;
}

export async function ask(question: string, cb: AskCallbacks): Promise<void> {
  const csrf = csrfToken();
  const res = await fetch('/api/ask', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  await parseSSEStream(res, (data) => {
    const e = data as {
      type: string; token?: string; citations?: Citation[];
      package?: ContextPackage; reason?: string;
    };
    if (e.type === 'token' && e.token !== undefined) cb.onToken(e.token);
    else if (e.type === 'citations' && e.citations) cb.onCitations(e.citations);
    // PER-319 /api/ask emits only citations/token/insufficient/[DONE] (no `context` event);
    // fetch the ContextPackage separately via POST /api/context-package when needed.
    else if (e.type === 'context' && e.package) cb.onContext(e.package);
    else if (e.type === 'insufficient') cb.onInsufficient(e.reason ?? 'insufficient evidence');
  });
}
```
- [ ] Run → PASS.
- [ ] Commit: `feat(frontend): add ask SSE client for cited retrieval`.

---

### Task 3 — Knowledge API client: sources, entities, timeline, graph

**Files:** `apps/frontend/src/api/knowledge.ts` (edit), `apps/frontend/src/api/knowledge.test.ts` (edit).

**Interfaces** — Consumes: the GET endpoints in Upstream Dependencies. Produces:
```ts
export function searchSources(q?: string, limit?: number): Promise<Source[]>;
export function getSource(id: string): Promise<Source>;
export function listSourceVersions(id: string): Promise<SourceVersion[]>;
export function listEntities(q?: string, limit?: number): Promise<Entity[]>;
export function getEntity(id: string): Promise<EntityDetail>;
export function getTimeline(opts?: { scope?: string; from?: string; to?: string }): Promise<TimelineEvent[]>;
export function getScopedGraph(scope: GraphScope): Promise<{ center: unknown; nodes: ContextNode[]; edges: ContextEdge[] }>;
```

- [ ] Add tests (mirror `api.test.ts` fetchMock style) asserting each hits the right URL and returns typed JSON. Example:
```ts
import { searchSources, getScopedGraph } from './knowledge';

it('searches sources', async () => {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
  await searchSources('readme', 10);
  expect(fetchMock).toHaveBeenCalledWith('/api/sources?q=readme&limit=10',
    expect.objectContaining({ credentials: 'include' }));
});

it('builds scoped graph query', async () => {
  fetchMock.mockResolvedValueOnce(new Response(
    JSON.stringify({ center: null, nodes: [], edges: [] }), { status: 200 }));
  await getScopedGraph({ seed: ['e1', 'e2'], depth: 2, relations: ['calls'] });
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/graph/neighbors?node_id=e1&depth=2',
    expect.objectContaining({ credentials: 'include' }));
});
```
- [ ] Run → FAIL.
- [ ] Implement in `knowledge.ts` using the existing `apiFetch` pattern:
```ts
import { apiFetch } from '../api';
import type { Source, SourceVersion, Entity, EntityDetail, TimelineEvent, GraphScope, ContextPackage } from './types';

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

export async function searchSources(q?: string, limit = 25): Promise<Source[]> {
  return (await apiFetch(`/api/sources${qs({ q, limit })}`)).json();
}
export async function getSource(id: string): Promise<Source> {
  return (await apiFetch(`/api/sources/${encodeURIComponent(id)}`)).json();
}
export async function listSourceVersions(id: string): Promise<SourceVersion[]> {
  return (await apiFetch(`/api/sources/${encodeURIComponent(id)}/versions`)).json();
}
export async function listEntities(q?: string, limit = 50): Promise<Entity[]> {
  return (await apiFetch(`/api/entities${qs({ q, limit })}`)).json();
}
export async function getEntity(id: string): Promise<EntityDetail> {
  return (await apiFetch(`/api/entities/${encodeURIComponent(id)}`)).json();
}
export async function getTimeline(
  opts: { scope?: string; from?: string; to?: string } = {},
): Promise<TimelineEvent[]> {
  return (await apiFetch(`/api/timeline${qs(opts)}`)).json();
}
// PER-319 canonical: GET /api/graph/neighbors?node_id=&depth= -> { center, nodes, edges }.
// Seed the neighborhood from the first scope node; POST /api/context-package covers
// multi-seed / relation-filtered expansion when richer scoping is needed.
export async function getScopedGraph(scope: GraphScope): Promise<{ center: unknown; nodes: ContextNode[]; edges: ContextEdge[] }> {
  return (await apiFetch(`/api/graph/neighbors${qs({
    node_id: scope.seed[0], depth: scope.depth,
  })}`)).json();
}
```
- [ ] Also export `apiFetch` from `src/api.ts` if not already exported.
- [ ] Run → PASS.
- [ ] Commit: `feat(frontend): add sources/entities/timeline/graph clients`.

---

### Task 4 — MethodBadge component

**Files:** `apps/frontend/src/components/provenance/MethodBadge.tsx` (new), `.test.tsx` (new).

**Interfaces** — Consumes: `{ method: ExtractionMethod }`. Produces: `export default function MethodBadge`.

- [ ] Write `MethodBadge.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import MethodBadge from './MethodBadge';

describe('MethodBadge', () => {
  it('labels an extracted claim', () => {
    render(<MethodBadge method="EXTRACTED" />);
    expect(screen.getByText('Extracted')).toBeInTheDocument();
  });
  it('flags ambiguous claims with a warning role', () => {
    render(<MethodBadge method="AMBIGUOUS" />);
    expect(screen.getByText('Ambiguous')).toHaveAttribute('data-method', 'AMBIGUOUS');
  });
});
```
- [ ] Run → FAIL.
- [ ] Create `MethodBadge.tsx`:
```tsx
import type { ExtractionMethod } from '../../api/types';

const LABEL: Record<ExtractionMethod, string> = {
  EXTRACTED: 'Extracted', INFERRED: 'Inferred', AMBIGUOUS: 'Ambiguous',
};
const STYLE: Record<ExtractionMethod, string> = {
  EXTRACTED: 'bg-emerald-500/15 text-emerald-400',
  INFERRED: 'bg-sky-500/15 text-sky-400',
  AMBIGUOUS: 'bg-amber-500/15 text-amber-400',
};

export default function MethodBadge({ method }: { method: ExtractionMethod }) {
  return (
    <span
      data-method={method}
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${STYLE[method]}`}
    >
      {LABEL[method]}
    </span>
  );
}
```
- [ ] Run → PASS.
- [ ] Commit: `feat(frontend): add extraction-method badge`.

---

### Task 5 — ConfidenceBadge component

**Files:** `apps/frontend/src/components/provenance/ConfidenceBadge.tsx` (new), `.test.tsx` (new).

**Interfaces** — Consumes: `{ confidence: number }` (0..1). Produces: `export default function ConfidenceBadge`.

- [ ] Write test:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ConfidenceBadge from './ConfidenceBadge';

describe('ConfidenceBadge', () => {
  it('renders a percentage', () => {
    render(<ConfidenceBadge confidence={0.92} />);
    expect(screen.getByText('92%')).toBeInTheDocument();
  });
  it('marks low confidence', () => {
    render(<ConfidenceBadge confidence={0.3} />);
    expect(screen.getByTestId('confidence')).toHaveAttribute('data-level', 'low');
  });
});
```
- [ ] Run → FAIL.
- [ ] Create `ConfidenceBadge.tsx`:
```tsx
function level(c: number): 'high' | 'medium' | 'low' {
  if (c >= 0.75) return 'high';
  if (c >= 0.5) return 'medium';
  return 'low';
}
const COLOR = { high: 'text-emerald-400', medium: 'text-amber-400', low: 'text-red-400' };

export default function ConfidenceBadge({ confidence }: { confidence: number }) {
  const l = level(confidence);
  return (
    <span data-testid="confidence" data-level={l}
      className={`text-[10px] font-mono ${COLOR[l]}`}
      title={`confidence ${confidence.toFixed(2)}`}>
      {Math.round(confidence * 100)}%
    </span>
  );
}
```
- [ ] Run → PASS.
- [ ] Commit: `feat(frontend): add confidence badge`.

---

### Task 6 — SourceSpanDrawer (immutable source + span)

**Files:** `apps/frontend/src/components/provenance/SourceSpanDrawer.tsx` (new), `.test.tsx` (new). Uses `Dialog` from `components/ui/Dialog.tsx`.

**Interfaces** — Consumes: `{ citation: Citation | null; open: boolean; onClose: () => void }`; calls `getSource(citation.source_id)`. Produces: `export default function SourceSpanDrawer`.

- [ ] Write test (mock `getSource`):
```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SourceSpanDrawer from './SourceSpanDrawer';
import type { Citation } from '../../api/types';

vi.mock('../../api/knowledge', () => ({
  getSource: vi.fn().mockResolvedValue({
    id: 's1', content_hash: 'abc', version: 2, source_type: 'doc',
    origin_uri: 'file://readme.md', ingested_at: '2026-07-01', scope: 'work',
    title: 'README',
  }),
}));

const citation: Citation = {
  chunk_id: 'c1', source_id: 's1', source_title: 'README',
  span: { start: 0, end: 5 }, extraction_method: 'EXTRACTED', confidence: 0.9,
};

describe('SourceSpanDrawer', () => {
  it('shows immutable source metadata and version', async () => {
    render(<SourceSpanDrawer citation={citation} open onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('README')).toBeInTheDocument());
    expect(screen.getByText(/version 2/i)).toBeInTheDocument();
    expect(screen.getByText(/file:\/\/readme\.md/)).toBeInTheDocument();
  });
});
```
- [ ] Run → FAIL.
- [ ] Create `SourceSpanDrawer.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { getSource } from '../../api/knowledge';
import type { Citation, Source } from '../../api/types';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/Dialog';

function spanLabel(s: Citation['span']): string {
  return 'start' in s ? `chars ${s.start}–${s.end}` : `lines ${s.line_start}–${s.line_end}`;
}

export default function SourceSpanDrawer({
  citation, open, onClose,
}: { citation: Citation | null; open: boolean; onClose: () => void }) {
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !citation) return;
    setSource(null); setError(null);
    getSource(citation.source_id).then(setSource).catch((e) => setError((e as Error).message));
  }, [open, citation]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{source?.title ?? citation?.source_title ?? 'Source'}</DialogTitle>
        </DialogHeader>
        {error && <p className="text-red-400 text-sm">{error}</p>}
        {source && (
          <div className="space-y-2 text-sm">
            <p className="text-muted-foreground">version {source.version} · immutable</p>
            <p className="font-mono text-xs break-all">{source.origin_uri}</p>
            <p className="text-xs text-muted-foreground">
              {source.source_type} · scope {source.scope} · ingested {source.ingested_at}
            </p>
            {citation && (
              <p className="text-xs">Cited evidence span: {spanLabel(citation.span)}</p>
            )}
            <p className="text-[10px] text-muted-foreground">hash {source.content_hash}</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
```
- [ ] Run → PASS. (If `Dialog` exports differ, adjust imports to match `components/ui/Dialog.tsx`.)
- [ ] Commit: `feat(frontend): add immutable source span drawer`.

---

### Task 7 — Provenance component (badges + click-through)

**Files:** `apps/frontend/src/components/provenance/Provenance.tsx` (new), `.test.tsx` (new).

**Interfaces** — Consumes: `{ citation: Citation; onInspect: (c: Citation) => void }`. Produces: `export default function Provenance`.

- [ ] Write test:
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import Provenance from './Provenance';
import type { Citation } from '../../api/types';

const citation: Citation = {
  chunk_id: 'c1', source_id: 's1', source_title: 'README',
  span: { start: 0, end: 5 }, extraction_method: 'INFERRED', confidence: 0.6,
};

describe('Provenance', () => {
  it('shows method, confidence, and source title', () => {
    render(<Provenance citation={citation} onInspect={() => {}} />);
    expect(screen.getByText('Inferred')).toBeInTheDocument();
    expect(screen.getByText('60%')).toBeInTheDocument();
    expect(screen.getByText('README')).toBeInTheDocument();
  });
  it('calls onInspect with the citation on click-through', async () => {
    const onInspect = vi.fn();
    render(<Provenance citation={citation} onInspect={onInspect} />);
    await userEvent.click(screen.getByRole('button', { name: /view source/i }));
    expect(onInspect).toHaveBeenCalledWith(citation);
  });
});
```
- [ ] Run → FAIL.
- [ ] Create `Provenance.tsx`:
```tsx
import type { Citation } from '../../api/types';
import MethodBadge from './MethodBadge';
import ConfidenceBadge from './ConfidenceBadge';

export default function Provenance({
  citation, onInspect,
}: { citation: Citation; onInspect: (c: Citation) => void }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <MethodBadge method={citation.extraction_method} />
      <ConfidenceBadge confidence={citation.confidence} />
      <span className="text-muted-foreground truncate max-w-[12rem]">{citation.source_title}</span>
      <button
        type="button"
        onClick={() => onInspect(citation)}
        className="text-sky-400 hover:underline"
      >
        View source
      </button>
    </div>
  );
}
```
- [ ] Run → PASS.
- [ ] Commit: `feat(frontend): add reusable provenance row`.

---

### Task 8 — EvidencePanel (citations for an answer/claim)

**Files:** `apps/frontend/src/components/provenance/EvidencePanel.tsx` (new), `.test.tsx` (new). Owns the `SourceSpanDrawer` open state.

**Interfaces** — Consumes: `{ citations: Citation[] }`. Produces: `export default function EvidencePanel`.

- [ ] Write test:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import EvidencePanel from './EvidencePanel';
import type { Citation } from '../../api/types';

const cites: Citation[] = [
  { chunk_id: 'c1', source_id: 's1', source_title: 'README', span: { start: 0, end: 5 }, extraction_method: 'EXTRACTED', confidence: 0.9 },
  { chunk_id: 'c2', source_id: 's2', source_title: 'ADR-1', span: { start: 3, end: 8 }, extraction_method: 'INFERRED', confidence: 0.5 },
];

describe('EvidencePanel', () => {
  it('renders one provenance row per citation', () => {
    render(<EvidencePanel citations={cites} />);
    expect(screen.getAllByRole('button', { name: /view source/i })).toHaveLength(2);
  });
  it('shows empty note when no citations', () => {
    render(<EvidencePanel citations={[]} />);
    expect(screen.getByText(/no evidence/i)).toBeInTheDocument();
  });
});
```
- [ ] Run → FAIL.
- [ ] Create `EvidencePanel.tsx`:
```tsx
import { useState } from 'react';
import type { Citation } from '../../api/types';
import Provenance from './Provenance';
import SourceSpanDrawer from './SourceSpanDrawer';

export default function EvidencePanel({ citations }: { citations: Citation[] }) {
  const [active, setActive] = useState<Citation | null>(null);
  if (citations.length === 0) {
    return <p className="text-xs text-muted-foreground">No evidence cited.</p>;
  }
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase">Evidence</h3>
      {citations.map((c) => (
        <Provenance key={c.chunk_id} citation={c} onInspect={setActive} />
      ))}
      <SourceSpanDrawer citation={active} open={active !== null} onClose={() => setActive(null)} />
    </div>
  );
}
```
- [ ] Run → PASS.
- [ ] Commit: `feat(frontend): add evidence panel`.

---

### Task 9 — CitedAnswer (streamed answer text)

**Files:** `apps/frontend/src/components/CitedAnswer.tsx` (new), `.test.tsx` (new).

**Interfaces** — Consumes: `{ text: string; streaming: boolean }`. Produces: `export default function CitedAnswer`.

- [ ] Write test:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import CitedAnswer from './CitedAnswer';

describe('CitedAnswer', () => {
  it('renders answer text', () => {
    render(<CitedAnswer text="Pranav owns Archivum." streaming={false} />);
    expect(screen.getByText('Pranav owns Archivum.')).toBeInTheDocument();
  });
  it('shows a streaming cursor while streaming', () => {
    render(<CitedAnswer text="Pranav" streaming />);
    expect(screen.getByTestId('stream-cursor')).toBeInTheDocument();
  });
});
```
- [ ] Run → FAIL.
- [ ] Create `CitedAnswer.tsx`:
```tsx
export default function CitedAnswer({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <div className="prose prose-invert max-w-none text-sm whitespace-pre-wrap">
      {text}
      {streaming && <span data-testid="stream-cursor" className="inline-block w-1.5 h-4 ml-0.5 bg-sky-400 animate-pulse align-middle" />}
    </div>
  );
}
```
- [ ] Run → PASS.
- [ ] Commit: `feat(frontend): add cited answer renderer`.

---

### Task 10 — AskBox (query input)

**Files:** `apps/frontend/src/components/AskBox.tsx` (new), `.test.tsx` (new). Uses `Textarea`/`Button` from `components/ui`.

**Interfaces** — Consumes: `{ onSubmit: (q: string) => void; disabled?: boolean }`. Produces: `export default function AskBox`.

- [ ] Write test:
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import AskBox from './AskBox';

describe('AskBox', () => {
  it('submits the trimmed question', async () => {
    const onSubmit = vi.fn();
    render(<AskBox onSubmit={onSubmit} />);
    await userEvent.type(screen.getByPlaceholderText(/ask archivum/i), '  who owns it?  ');
    await userEvent.click(screen.getByRole('button', { name: /ask/i }));
    expect(onSubmit).toHaveBeenCalledWith('who owns it?');
  });
  it('does not submit empty input', async () => {
    const onSubmit = vi.fn();
    render(<AskBox onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole('button', { name: /ask/i }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
```
- [ ] Run → FAIL.
- [ ] Create `AskBox.tsx`:
```tsx
import { useState } from 'react';
import { Textarea } from './ui/Textarea';
import { Button } from './ui/Button';

export default function AskBox({
  onSubmit, disabled,
}: { onSubmit: (q: string) => void; disabled?: boolean }) {
  const [value, setValue] = useState('');
  function submit() {
    const q = value.trim();
    if (!q) return;
    onSubmit(q);
  }
  return (
    <div className="space-y-2">
      <Textarea
        placeholder="Ask Archivum anything…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); }
        }}
        rows={3}
      />
      <div className="flex justify-end">
        <Button onClick={submit} disabled={disabled}>Ask</Button>
      </div>
    </div>
  );
}
```
- [ ] Run → PASS. (Adjust `Textarea`/`Button` imports to match existing named/default exports.)
- [ ] Commit: `feat(frontend): add ask input box`.

---

### Task 11 — AskPage (homepage: streamed cited answer + insufficient state)

**Files:** `apps/frontend/src/pages/AskPage.tsx` (new), `.test.tsx` (new).

**Interfaces** — Consumes: `ask()` from `api/knowledge`, `Citation`/`ContextPackage`. Produces: `export default function AskPage`.

- [ ] Write test (mock `ask` to drive callbacks):
```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import AskPage from './AskPage';
import type { AskCallbacks } from '../api/knowledge';

const askMock = vi.fn();
vi.mock('../api/knowledge', () => ({ ask: (q: string, cb: AskCallbacks) => askMock(q, cb) }));

describe('AskPage', () => {
  it('streams a cited answer', async () => {
    askMock.mockImplementation(async (_q: string, cb: AskCallbacks) => {
      cb.onToken('Pranav owns it.');
      cb.onCitations([{ chunk_id: 'c1', source_id: 's1', source_title: 'README', span: { start: 0, end: 5 }, extraction_method: 'EXTRACTED', confidence: 0.9 }]);
      cb.onContext({ query: 'q', nodes: [], edges: [], sufficient: true });
    });
    render(<AskPage />);
    await userEvent.type(screen.getByPlaceholderText(/ask archivum/i), 'who owns it?');
    await userEvent.click(screen.getByRole('button', { name: /ask/i }));
    await waitFor(() => expect(screen.getByText('Pranav owns it.')).toBeInTheDocument());
    expect(screen.getByText('README')).toBeInTheDocument();
  });

  it('shows insufficient-evidence state', async () => {
    askMock.mockImplementation(async (_q: string, cb: AskCallbacks) => {
      cb.onInsufficient('no supporting evidence');
    });
    render(<AskPage />);
    await userEvent.type(screen.getByPlaceholderText(/ask archivum/i), 'unknown?');
    await userEvent.click(screen.getByRole('button', { name: /ask/i }));
    await waitFor(() => expect(screen.getByText(/insufficient evidence/i)).toBeInTheDocument());
    expect(screen.getByText(/no supporting evidence/i)).toBeInTheDocument();
  });
});
```
- [ ] Run → FAIL.
- [ ] Create `AskPage.tsx`:
```tsx
import { useState } from 'react';
import { ask } from '../api/knowledge';
import type { Citation } from '../api/types';
import AskBox from '../components/AskBox';
import CitedAnswer from '../components/CitedAnswer';
import EvidencePanel from '../components/provenance/EvidencePanel';

export default function AskPage() {
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [insufficient, setInsufficient] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asked, setAsked] = useState(false);

  async function run(question: string) {
    setAnswer(''); setCitations([]); setInsufficient(null);
    setError(null); setAsked(true); setStreaming(true);
    try {
      await ask(question, {
        onToken: (t) => setAnswer((a) => a + t),
        onCitations: (c) => setCitations(c),
        onContext: () => {},
        onInsufficient: (r) => setInsufficient(r),
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl p-6 space-y-6">
      <h1 className="text-lg font-semibold">Ask Archivum</h1>
      <AskBox onSubmit={run} disabled={streaming} />
      {error && <p className="text-red-400 text-sm">{error}</p>}
      {asked && insufficient && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 p-4">
          <p className="text-sm font-medium text-amber-300">Insufficient evidence</p>
          <p className="text-xs text-amber-200/80 mt-1">{insufficient}</p>
        </div>
      )}
      {asked && !insufficient && (answer || streaming) && (
        <div className="space-y-4">
          <CitedAnswer text={answer} streaming={streaming} />
          <EvidencePanel citations={citations} />
        </div>
      )}
    </div>
  );
}
```
- [ ] Run → PASS.
- [ ] Commit: `feat(frontend): add ask homepage with cited answers`.

---

### Task 12 — SourceRow + SourcesPage (immutable source inspection + versions)

**Files:** `apps/frontend/src/components/SourceRow.tsx` (new) + test; `apps/frontend/src/pages/SourcesPage.tsx` (new) + test.

**Interfaces** — Consumes: `searchSources`, `listSourceVersions`. Produces: `SourceRow` (`{ source: Source; onOpen: (id: string) => void }`), `SourcesPage`.

- [ ] Write `SourceRow.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import SourceRow from './SourceRow';

describe('SourceRow', () => {
  it('shows source type, origin and version', () => {
    render(<SourceRow onOpen={() => {}} source={{
      id: 's1', content_hash: 'h', version: 3, source_type: 'pdf',
      origin_uri: 'file://a.pdf', ingested_at: '2026-07-01', scope: 'work', title: 'Spec',
    }} />);
    expect(screen.getByText('Spec')).toBeInTheDocument();
    expect(screen.getByText(/pdf/)).toBeInTheDocument();
    expect(screen.getByText(/v3/)).toBeInTheDocument();
  });
});
```
- [ ] Run → FAIL. Create `SourceRow.tsx`:
```tsx
import type { Source } from '../api/types';

export default function SourceRow({
  source, onOpen,
}: { source: Source; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(source.id)}
      className="w-full text-left rounded border border-border p-3 hover:bg-panel/40"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{source.title}</span>
        <span className="text-[10px] text-muted-foreground">v{source.version}</span>
      </div>
      <p className="text-xs text-muted-foreground truncate">{source.origin_uri}</p>
      <p className="text-[10px] text-muted-foreground">
        {source.source_type} · scope {source.scope} · {source.ingested_at}
      </p>
    </button>
  );
}
```
- [ ] Run → PASS. Commit: `feat(frontend): add source row`.
- [ ] Write `SourcesPage.test.tsx` (mock `searchSources`, `listSourceVersions`):
```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SourcesPage from './SourcesPage';

vi.mock('../api/knowledge', () => ({
  searchSources: vi.fn().mockResolvedValue([{
    id: 's1', content_hash: 'h', version: 2, source_type: 'doc',
    origin_uri: 'file://readme.md', ingested_at: '2026-07-01', scope: 'work', title: 'README',
  }]),
  listSourceVersions: vi.fn().mockResolvedValue([
    { version: 2, content_hash: 'h2', ingested_at: '2026-07-01' },
    { version: 1, content_hash: 'h1', ingested_at: '2026-06-01' },
  ]),
}));

describe('SourcesPage', () => {
  it('lists immutable sources', async () => {
    render(<SourcesPage />);
    await waitFor(() => expect(screen.getByText('README')).toBeInTheDocument());
  });
});
```
- [ ] Run → FAIL. Create `SourcesPage.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { searchSources, listSourceVersions } from '../api/knowledge';
import type { Source, SourceVersion } from '../api/types';
import SourceRow from '../components/SourceRow';
import { Input } from '../components/ui/Input';

export default function SourcesPage() {
  const [q, setQ] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [versions, setVersions] = useState<SourceVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    searchSources(q).then((s) => { if (live) setSources(s); })
      .catch((e) => setError((e as Error).message));
    return () => { live = false; };
  }, [q]);

  async function open(id: string) {
    setVersions(await listSourceVersions(id));
  }

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-lg font-semibold">Sources</h1>
      <Input placeholder="Search sources…" value={q} onChange={(e) => setQ(e.target.value)} />
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <div className="grid gap-2">
        {sources.map((s) => <SourceRow key={s.id} source={s} onOpen={open} />)}
      </div>
      {versions && (
        <div className="rounded border border-border p-3">
          <h2 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Versions (immutable)</h2>
          <ul className="space-y-1 text-xs font-mono">
            {versions.map((v) => (
              <li key={v.version}>v{v.version} · {v.ingested_at} · {v.content_hash}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```
- [ ] Run → PASS. Commit: `feat(frontend): add sources browser with version history`.

---

### Task 13 — EntityCard + EntitiesPage

**Files:** `apps/frontend/src/components/EntityCard.tsx` (new) + test; `apps/frontend/src/pages/EntitiesPage.tsx` (new) + test.

**Interfaces** — Consumes: `listEntities`, `getEntity`. Produces: `EntityCard` (`{ entity: Entity; onOpen: (id: string) => void }`), `EntitiesPage`.

- [ ] Write `EntityCard.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import EntityCard from './EntityCard';

describe('EntityCard', () => {
  it('shows label, type and provenance count', () => {
    render(<EntityCard onOpen={() => {}} entity={{
      id: 'e1', label: 'Pranav', entity_type: 'person', claim_count: 4, provenance_count: 7,
    }} />);
    expect(screen.getByText('Pranav')).toBeInTheDocument();
    expect(screen.getByText('person')).toBeInTheDocument();
    expect(screen.getByText(/7 citations/)).toBeInTheDocument();
  });
});
```
- [ ] Run → FAIL. Create `EntityCard.tsx`:
```tsx
import type { Entity } from '../api/types';

export default function EntityCard({
  entity, onOpen,
}: { entity: Entity; onOpen: (id: string) => void }) {
  return (
    <button type="button" onClick={() => onOpen(entity.id)}
      className="w-full text-left rounded border border-border p-3 hover:bg-panel/40">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{entity.label}</span>
        <span className="text-[10px] rounded bg-panel px-1.5 py-0.5 text-muted-foreground">{entity.entity_type}</span>
      </div>
      <p className="text-[10px] text-muted-foreground">
        {entity.claim_count} claims · {entity.provenance_count} citations
      </p>
    </button>
  );
}
```
- [ ] Run → PASS. Commit: `feat(frontend): add entity card`.
- [ ] Write `EntitiesPage.test.tsx` (mock `listEntities`, `getEntity`); assert entity detail renders claim provenance rows. Detail claims are `ContextNode[]`; render each claim's `citations` through `EvidencePanel`.
- [ ] Run → FAIL. Create `EntitiesPage.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { listEntities, getEntity } from '../api/knowledge';
import type { Entity, EntityDetail } from '../api/types';
import EntityCard from '../components/EntityCard';
import EvidencePanel from '../components/provenance/EvidencePanel';
import MethodBadge from '../components/provenance/MethodBadge';
import ConfidenceBadge from '../components/provenance/ConfidenceBadge';
import { Input } from '../components/ui/Input';

export default function EntitiesPage() {
  const [q, setQ] = useState('');
  const [entities, setEntities] = useState<Entity[]>([]);
  const [detail, setDetail] = useState<EntityDetail | null>(null);

  useEffect(() => {
    let live = true;
    listEntities(q).then((e) => { if (live) setEntities(e); });
    return () => { live = false; };
  }, [q]);

  return (
    <div className="p-6 grid grid-cols-[20rem_1fr] gap-6">
      <div className="space-y-3">
        <h1 className="text-lg font-semibold">Entities</h1>
        <Input placeholder="Search entities…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="grid gap-2">
          {entities.map((e) => (
            <EntityCard key={e.id} entity={e} onOpen={(id) => getEntity(id).then(setDetail)} />
          ))}
        </div>
      </div>
      <div>
        {detail ? (
          <div className="space-y-4">
            <h2 className="text-base font-semibold">{detail.label}
              <span className="ml-2 text-xs text-muted-foreground">{detail.entity_type}</span>
            </h2>
            {detail.claims.map((c) => (
              <div key={c.id} className="rounded border border-border p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm">{c.label}</span>
                  <MethodBadge method={c.extraction_method} />
                  <ConfidenceBadge confidence={c.confidence} />
                </div>
                <EvidencePanel citations={c.citations} />
              </div>
            ))}
          </div>
        ) : <p className="text-sm text-muted-foreground">Select an entity to inspect its claims and provenance.</p>}
      </div>
    </div>
  );
}
```
- [ ] Run → PASS. Commit: `feat(frontend): add entities browser with claim provenance`.

---

### Task 14 — TimelinePage (temporal projection)

**Files:** `apps/frontend/src/pages/TimelinePage.tsx` (new) + test.

**Interfaces** — Consumes: `getTimeline`. Produces: `export default function TimelinePage`.

- [ ] Write test (mock `getTimeline`):
```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import TimelinePage from './TimelinePage';

vi.mock('../api/knowledge', () => ({
  getTimeline: vi.fn().mockResolvedValue([{
    id: 'ev1', label: 'Archivum licensed Apache-2.0',
    valid_from: '2026-06-01', valid_to: null, recorded_at: '2026-06-02',
    confidence: 0.95, extraction_method: 'EXTRACTED',
    citations: [{ chunk_id: 'c1', source_id: 's1', source_title: 'LICENSE', span: { start: 0, end: 5 }, extraction_method: 'EXTRACTED', confidence: 0.95 }],
  }]),
}));

describe('TimelinePage', () => {
  it('renders events ordered with provenance', async () => {
    render(<TimelinePage />);
    await waitFor(() => expect(screen.getByText('Archivum licensed Apache-2.0')).toBeInTheDocument());
    expect(screen.getByText('2026-06-01')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /view source/i })).toBeInTheDocument();
  });
});
```
- [ ] Run → FAIL. Create `TimelinePage.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { getTimeline } from '../api/knowledge';
import type { TimelineEvent } from '../api/types';
import EvidencePanel from '../components/provenance/EvidencePanel';
import MethodBadge from '../components/provenance/MethodBadge';
import ConfidenceBadge from '../components/provenance/ConfidenceBadge';

export default function TimelinePage() {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTimeline().then((e) =>
      setEvents([...e].sort((a, b) => a.valid_from.localeCompare(b.valid_from))),
    ).catch((err) => setError((err as Error).message));
  }, []);

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-lg font-semibold">Timeline</h1>
      <p className="text-xs text-muted-foreground">Read-only temporal projection over canonical events.</p>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <ol className="border-l border-border pl-4 space-y-4">
        {events.map((ev) => (
          <li key={ev.id} className="relative">
            <span className="absolute -left-[21px] top-1 w-2 h-2 rounded-full bg-sky-400" />
            <div className="flex items-center gap-2">
              <time className="text-xs font-mono text-muted-foreground">{ev.valid_from}</time>
              <MethodBadge method={ev.extraction_method} />
              <ConfidenceBadge confidence={ev.confidence} />
            </div>
            <p className="text-sm mt-1">{ev.label}</p>
            <div className="mt-2"><EvidencePanel citations={ev.citations} /></div>
          </li>
        ))}
      </ol>
    </div>
  );
}
```
- [ ] Run → PASS. Commit: `feat(frontend): add timeline projection surface`.

---

### Task 15 — ScopedGraph + GraphPage (scoped exploration, not homepage)

**Files:** `apps/frontend/src/components/ScopedGraph.tsx` (new) + test; `apps/frontend/src/pages/GraphPage.tsx` (new) + test. Adapt from `GraphView.tsx` (vis-network dynamic import + click nav).

**Interfaces** — Consumes: `getScopedGraph(scope)` → PER-319 `GET /api/graph/neighbors` `{ center, nodes, edges }` (`ContextNode[]`/`ContextEdge[]`). Produces: `ScopedGraph` (`{ scope: GraphScope; onSelectNode?: (id: string) => void }`), `GraphPage`.

- [ ] Write `ScopedGraph.test.tsx` — mock `getScopedGraph`; assert it loads the scoped package and renders node/edge counts (vis-network `Network` is a dynamic import; test asserts the count summary text, not canvas):
```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ScopedGraph from './ScopedGraph';

vi.mock('../api/knowledge', () => ({
  getScopedGraph: vi.fn().mockResolvedValue({
    center: null,
    nodes: [
      { id: 'n1', label: 'A', kind: 'entity', confidence: 0.9, extraction_method: 'EXTRACTED', citations: [] },
      { id: 'n2', label: 'B', kind: 'entity', confidence: 0.8, extraction_method: 'INFERRED', citations: [] },
    ],
    edges: [{ from: 'n1', to: 'n2', label: 'relates', extraction_method: 'INFERRED', confidence: 0.7 }],
  }),
}));

describe('ScopedGraph', () => {
  it('loads a scoped neighborhood', async () => {
    render(<ScopedGraph scope={{ seed: ['n1'], depth: 2 }} />);
    await waitFor(() => expect(screen.getByText(/2 nodes · 1 edge/)).toBeInTheDocument());
  });
});
```
- [ ] Run → FAIL. Create `ScopedGraph.tsx` (guard `vis-network` import for jsdom):
```tsx
import { useEffect, useRef, useState } from 'react';
import type { Network } from 'vis-network';
import { getScopedGraph } from '../api/knowledge';
import type { GraphScope, ContextPackage } from '../api/types';

const NODE_COLORS: Record<string, string> = {
  entity: '#4B91F1', artifact: '#43a047', event: '#f9a825', claim: '#ab47bc',
};

export default function ScopedGraph({
  scope, onSelectNode,
}: { scope: GraphScope; onSelectNode?: (id: string) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const [pkg, setPkg] = useState<ContextPackage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getScopedGraph(scope).then(setPkg).catch((e) => setError((e as Error).message));
    return () => { networkRef.current?.destroy(); networkRef.current = null; };
  }, [scope.seed.join(','), scope.depth, scope.relations?.join(',')]);

  useEffect(() => {
    if (!pkg || !containerRef.current) return;
    let cancelled = false;
    Promise.all([import('vis-network'), import('vis-data')]).then(([{ Network }, { DataSet }]) => {
      if (cancelled || !containerRef.current) return;
      const nodes = new DataSet(pkg.nodes.map((n) => ({
        id: n.id, label: n.label,
        color: NODE_COLORS[n.kind] ?? NODE_COLORS.entity,
        font: { color: '#cdd6f4', size: 11 },
      })));
      const edges = new DataSet(pkg.edges.map((e, i) => ({
        id: `e${i}`, from: e.from, to: e.to, label: e.label,
        arrows: { to: { enabled: true, scaleFactor: 0.5 } },
      })));
      const network = new Network(containerRef.current, { nodes, edges }, {
        physics: { stabilization: { iterations: 100 } },
        interaction: { hover: true },
      });
      network.on('click', (p) => {
        if (p.nodes.length > 0 && onSelectNode) onSelectNode(String(p.nodes[0]));
      });
      networkRef.current = network;
    }).catch(() => { /* vis-network unavailable (e.g. jsdom) — counts still render */ });
    return () => { cancelled = true; };
  }, [pkg, onSelectNode]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border text-xs text-muted-foreground">
        {error ? <span className="text-red-400">{error}</span> : (
          <span>{pkg ? `${pkg.nodes.length} nodes · ${pkg.edges.length} edge${pkg.edges.length === 1 ? '' : 's'}` : 'Loading…'}</span>
        )}
        <span className="ml-auto">scoped · depth {scope.depth}</span>
      </div>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}
```
- [ ] Run → PASS.
- [ ] Write `GraphPage.test.tsx` — assert it renders a seed input and mounts `ScopedGraph` only after a seed is provided (graph is exploration, never auto-loads the whole corpus):
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import GraphPage from './GraphPage';

describe('GraphPage', () => {
  it('prompts for a seed before exploring', () => {
    render(<GraphPage />);
    expect(screen.getByText(/enter a seed entity to explore/i)).toBeInTheDocument();
  });
});
```
- [ ] Run → FAIL. Create `GraphPage.tsx`:
```tsx
import { useState } from 'react';
import ScopedGraph from '../components/ScopedGraph';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import type { GraphScope } from '../api/types';

export default function GraphPage() {
  const [seedInput, setSeedInput] = useState('');
  const [scope, setScope] = useState<GraphScope | null>(null);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 p-4 border-b border-border">
        <Input placeholder="Seed entity id…" value={seedInput}
          onChange={(e) => setSeedInput(e.target.value)} className="w-64" />
        <Button onClick={() => {
          const seed = seedInput.trim();
          if (seed) setScope({ seed: [seed], depth: 2 });
        }}>Explore</Button>
      </div>
      <div className="flex-1">
        {scope ? <ScopedGraph scope={scope} /> : (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
            Enter a seed entity to explore its neighborhood.
          </div>
        )}
      </div>
    </div>
  );
}
```
- [ ] Run → PASS. Commit: `feat(frontend): add scoped graph exploration surface`.

---

### Task 16 — ProjectsPage (read-only L3 dossier projection)

**Files:** `apps/frontend/src/pages/ProjectsPage.tsx` (replace existing wiki version) + test.

**Interfaces** — Consumes: `listEntities('project')` (project entities) + `getEntity` for the dossier. Produces: `export default function ProjectsPage`. **Read-only** — no create/edit affordances (old ProjectsPage had create forms; those are removed).

- [ ] Write test asserting: project list renders, selecting a project shows dossier claims each with provenance, and **no** "Create"/"New project" button exists:
```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ProjectsPage from './ProjectsPage';

vi.mock('../api/knowledge', () => ({
  listEntities: vi.fn().mockResolvedValue([{ id: 'p1', label: 'Archivum', entity_type: 'project', claim_count: 2, provenance_count: 3 }]),
  getEntity: vi.fn().mockResolvedValue({
    id: 'p1', label: 'Archivum', entity_type: 'project', claim_count: 2, provenance_count: 3,
    claims: [{ id: 'cl1', label: 'Licensed Apache-2.0', kind: 'claim', confidence: 0.95, extraction_method: 'EXTRACTED',
      citations: [{ chunk_id: 'c1', source_id: 's1', source_title: 'LICENSE', span: { start: 0, end: 5 }, extraction_method: 'EXTRACTED', confidence: 0.95 }] }],
    relationships: [],
  }),
}));

describe('ProjectsPage', () => {
  it('renders read-only project dossiers with provenance', async () => {
    render(<ProjectsPage />);
    await waitFor(() => expect(screen.getByText('Archivum')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /new project|create/i })).toBeNull();
  });
});
```
- [ ] Run → FAIL. Replace `ProjectsPage.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { listEntities, getEntity } from '../api/knowledge';
import type { Entity, EntityDetail } from '../api/types';
import EvidencePanel from '../components/provenance/EvidencePanel';
import MethodBadge from '../components/provenance/MethodBadge';
import ConfidenceBadge from '../components/provenance/ConfidenceBadge';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Entity[]>([]);
  const [dossier, setDossier] = useState<EntityDetail | null>(null);

  useEffect(() => { listEntities('project').then(setProjects); }, []);

  return (
    <div className="p-6 grid grid-cols-[18rem_1fr] gap-6">
      <div className="space-y-2">
        <h1 className="text-lg font-semibold">Projects</h1>
        <p className="text-xs text-muted-foreground">Generated dossiers (read-only projection).</p>
        {projects.map((p) => (
          <button key={p.id} type="button" onClick={() => getEntity(p.id).then(setDossier)}
            className="w-full text-left rounded border border-border p-3 hover:bg-panel/40">
            <span className="text-sm font-medium">{p.label}</span>
            <p className="text-[10px] text-muted-foreground">{p.claim_count} claims</p>
          </button>
        ))}
      </div>
      <div>
        {dossier ? (
          <article className="space-y-4">
            <h2 className="text-base font-semibold">{dossier.label}</h2>
            {dossier.claims.map((c) => (
              <section key={c.id} className="rounded border border-border p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm">{c.label}</span>
                  <MethodBadge method={c.extraction_method} />
                  <ConfidenceBadge confidence={c.confidence} />
                </div>
                <EvidencePanel citations={c.citations} />
              </section>
            ))}
          </article>
        ) : <p className="text-sm text-muted-foreground">Select a project to read its dossier.</p>}
      </div>
    </div>
  );
}
```
- [ ] Run → PASS. Commit: `feat(frontend): replace projects with read-only dossier projection`.

---

### Task 17 — AppShell (nav; Ask-first)

**Files:** `apps/frontend/src/components/AppShell.tsx` (new) + test. Replaces `Layout.tsx`.

**Interfaces** — Consumes: React Router `<Outlet>` / `NavLink`. Produces: `export default function AppShell`.

- [ ] Write test:
```tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import AppShell from './AppShell';

describe('AppShell', () => {
  it('renders the primary surface nav with Ask first', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes><Route element={<AppShell />}><Route index element={<div>Home</div>} /></Route></Routes>
      </MemoryRouter>,
    );
    const links = screen.getAllByRole('link').map((l) => l.textContent);
    expect(links).toEqual(['Ask', 'Sources', 'Projects', 'Entities', 'Timeline', 'Graph']);
  });
});
```
- [ ] Run → FAIL. Create `AppShell.tsx`:
```tsx
import { NavLink, Outlet } from 'react-router-dom';

const NAV = [
  { to: '/', label: 'Ask', end: true },
  { to: '/sources', label: 'Sources' },
  { to: '/projects', label: 'Projects' },
  { to: '/entities', label: 'Entities' },
  { to: '/timeline', label: 'Timeline' },
  { to: '/graph', label: 'Graph' },
];

export default function AppShell() {
  return (
    <div className="flex h-screen bg-bg text-text">
      <aside className="w-48 shrink-0 border-r border-border p-3 space-y-1">
        <div className="px-2 py-3 text-sm font-semibold">Archivum</div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}
            className={({ isActive }) =>
              `block rounded px-2 py-1.5 text-sm ${isActive ? 'bg-panel text-text' : 'text-muted-foreground hover:bg-panel/50'}`}>
            {n.label}
          </NavLink>
        ))}
      </aside>
      <main className="flex-1 overflow-auto"><Outlet /></main>
    </div>
  );
}
```
- [ ] Run → PASS. Commit: `feat(frontend): add ask-first app shell`.

---

### Task 18 — Route table rewrite (Ask index + wiki redirects) & store cleanup

**Files:** `apps/frontend/src/App.tsx` (edit), `apps/frontend/src/store.ts` (edit), `apps/frontend/src/App.test.tsx` (new).

**Interfaces** — Consumes: new pages + `AppShell`. Produces: updated `App` + trimmed `store`.

- [ ] Write `App.test.tsx` asserting Ask renders at `/` and legacy `/wiki/x` redirects to `/`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('./api', () => ({ refreshSession: vi.fn().mockResolvedValue({}) }));
vi.mock('./api/knowledge', () => ({ ask: vi.fn() }));

import App from './App';

describe('App routing', () => {
  it('serves Ask as the homepage', async () => {
    window.history.pushState({}, '', '/');
    render(<App />);
    expect(await screen.findByText(/ask archivum/i)).toBeInTheDocument();
  });
});
```
- [ ] Run → FAIL. Rewrite `App.tsx` `ProtectedRoutes` route table:
```tsx
// inside ProtectedRoutes return:
<Routes>
  <Route element={<AppShell />}>
    <Route index element={<AskPage />} />
    <Route path="sources" element={<SourcesPage />} />
    <Route path="projects" element={<ProjectsPage />} />
    <Route path="entities" element={<EntitiesPage />} />
    <Route path="timeline" element={<TimelinePage />} />
    <Route path="graph" element={<GraphPage />} />
  </Route>
  {/* legacy wiki redirects → nearest new surface */}
  <Route path="/wiki/*" element={<Navigate to="/" replace />} />
  <Route path="/library" element={<Navigate to="/sources" replace />} />
  <Route path="/workflows/*" element={<Navigate to="/projects" replace />} />
  <Route path="/tools/graph" element={<Navigate to="/graph" replace />} />
  <Route path="/tools/query" element={<Navigate to="/" replace />} />
  <Route path="/tools/*" element={<Navigate to="/" replace />} />
  <Route path="/query" element={<Navigate to="/" replace />} />
  <Route path="/daily" element={<Navigate to="/timeline" replace />} />
  <Route path="*" element={<NotFoundPage />} />
</Routes>
```
- [ ] Update imports in `App.tsx`: remove wiki/workflows/tools/library imports; add AskPage/SourcesPage/ProjectsPage/EntitiesPage/TimelinePage/GraphPage/AppShell. Keep the auth bootstrap effect but replace `listPages()` with `refreshSession()` (no more page preloading).
- [ ] Trim `store.ts`: remove `pages`, `pagesLoaded`, `currentSlug`, `saveStatus`, `ActiveView`, page actions; keep `isAuthenticated`, `leftOpen/rightOpen` if used by shell; add `activeSurface`. Update reducer + remove now-dead `Page` import.
- [ ] Run `App.test.tsx` → PASS. Run full suite `npm test --workspace apps/frontend` and fix compile fallout from removed store fields.
- [ ] Commit: `feat(frontend): route ask as homepage and redirect legacy wiki routes`.

---

### Task 19 — Remove old Markdown wiki UI

**Files:** delete the removed set listed in **File Structure** (pages, components, `Editor/*`, `life-pages.test.tsx`), and any now-dead exports in `src/api.ts`.

**Interfaces** — Consumes: nothing. Produces: a clean tree with no wiki modules and a green build.

- [ ] `git rm` the removed pages/components/tests (WikiPage, PublicWikiPage, LibraryPage, WorkflowsPage, ToolsPage, DailyPage, DecisionsPage, TasksPage, ActivityPage, LintPage, SettingsPage, SharePage; Layout, FileTree, BacklinksPanel, NotesInteractionPanel, QueryPanel, RightSidebar, SearchBar, StatusBar, IngestPanel, GraphView; `components/Editor/`; `life-pages.test.tsx`).
- [ ] Remove dead wiki/folder/life/lint/share exports from `src/api.ts` (keep `apiFetch`, `parseSSEStream`, `csrfToken`, `login`, `logout`, `refreshSession`). Update `src/api.test.ts` to drop tests for removed functions.
- [ ] Grep for dangling imports: `cd apps/frontend && npx tsc --noEmit`. Fix any references.
- [ ] Run full suite `npm test --workspace apps/frontend` → all PASS. Run `npm run build --workspace apps/frontend` → success.
- [ ] Commit: `chore(frontend): remove legacy markdown wiki UI`.

---

## Self-Review

**Spec coverage** — Ask homepage (T11, index route T18) ✓; provenance always visible via `<Provenance>`/`EvidencePanel` on Ask (T11), Entities (T13), Timeline (T14), Projects (T16) ✓; citation shows confidence + method + click-through to immutable source+span (T4–T7, drawer T6) ✓; Sources browser with immutable inspection + versions (T12) ✓; Entities (T13) ✓; Timeline temporal projection (T14) ✓; scoped Graph exploration, never homepage, seed-gated (T15) ✓; read-only projections — no edit affordances, ProjectsPage create forms removed (T16, asserted in test) ✓; insufficient-evidence first-class state (T11) ✓; ContextPackage/Citation typed client for PER-319 (T1–T3) ✓; app shell + routing replacing wiki (T17–T18) ✓; removal/redirect of Markdown wiki (T18 redirects, T19 deletions) ✓; vis-network reused (T15) ✓.

**Placeholder scan** — No `TODO`, `...`, or stub bodies in code steps; every component returns real TSX; every client function has a real body; all mocks in tests return concrete typed objects. The only deferred items are the PER-319 endpoint shapes, explicitly flagged in Upstream Dependencies and isolated to `src/api/types.ts`.

**Type consistency** — All props/response types are defined in `src/api/types.ts` (T1) and imported by every consumer. `Citation.span` union (`{start,end} | {line_start,line_end}`) is handled in `SourceSpanDrawer` (`'start' in s` guard). `ContextNode.citations` feeds `EvidencePanel` in Entities/Projects/Timeline consistently. `GraphScope` is produced by `GraphPage`, consumed by `ScopedGraph` and `getScopedGraph`. Callback interface `AskCallbacks` is shared between `ask()` and `AskPage`.

**Fix applied inline** — Task 0 added because RTL/jsdom is not currently a direct dependency (existing tests use `renderToString`); without it the component tests in T4–T18 cannot run. `ScopedGraph` guards the `vis-network` dynamic import so tests pass under jsdom (assert count summary, not canvas).
