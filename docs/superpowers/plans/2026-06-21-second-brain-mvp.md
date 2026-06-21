# Second-Brain MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Archivum into a functioning local-first MCP server and Obsidian-like second-brain interface for personal knowledge, Life OS workflows, and project memory.

**Architecture:** Keep the current FastAPI + React + FastMCP stack. Store portable canonical knowledge in markdown pages, add normalized SQLite tables for Life OS entities and agent activity, keep Qdrant for semantic search, and keep Kuzu for graph traversal. Expose every core workflow through both REST and MCP so browser use and agent use stay equivalent.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, Qdrant, Kuzu, FastMCP, React 18, Vite, TypeScript, CodeMirror 6, Tailwind, Vitest, pytest, Docker Compose.

---

## File Structure

- Modify: `progress.md` - root project progress tracker for this MVP.
- Create: `docs/project/life-os-conventions.md` - user-facing conventions for pages, tags, frontmatter, folders, and agent-safe writes.
- Modify: `README.md` - add personal second-brain setup, Life OS workflow, MCP client config, and backup/restore sections.
- Modify: `apps/backend/archivum/db/sqlite.py` - add Life OS and agent activity tables plus CRUD helpers.
- Create: `apps/backend/archivum/life_os/models.py` - typed request/response models shared by API and MCP.
- Create: `apps/backend/archivum/life_os/service.py` - business logic for daily notes, projects, tasks, decisions, people, areas, and activity log.
- Create: `apps/backend/archivum/api/life_os.py` - REST endpoints for the Life OS workflows.
- Modify: `apps/backend/archivum/main.py` - mount the Life OS API router.
- Modify: `apps/backend/archivum/mcp/server.py` - expose Life OS MCP tools.
- Modify: `apps/backend/archivum/api/search.py` and `apps/backend/archivum/db/sqlite.py` - confirm or add hybrid semantic + FTS search.
- Modify: `apps/frontend/src/api.ts` and `apps/frontend/src/types.ts` - add Life OS client methods and types.
- Modify: `apps/frontend/src/App.tsx` and `apps/frontend/src/components/Layout.tsx` - add routes/navigation for Daily, Projects, Tasks, Decisions, and Activity.
- Create: `apps/frontend/src/pages/DailyPage.tsx` - daily note workflow.
- Create: `apps/frontend/src/pages/ProjectsPage.tsx` - project registry and project memory dashboard.
- Create: `apps/frontend/src/pages/TasksPage.tsx` - task capture and review.
- Create: `apps/frontend/src/pages/DecisionsPage.tsx` - decision log.
- Create: `apps/frontend/src/pages/ActivityPage.tsx` - ingest/MCP/agent activity timeline.
- Modify: `apps/frontend/src/components/SearchBar.tsx` - display hybrid search result source and Life OS metadata.
- Create/modify tests under `tests/`, `tests/api/`, `tests/mcp_tests/`, and `apps/frontend/src/*.test.tsx`.

---

## Milestone 0: Baseline Verification And Doc Reconciliation

### Task 0.1: Verify Existing Backend, Frontend, MCP, And Docker Entry Points

**Files:**
- Modify: `progress.md`
- Modify: `docs/project/progress.md`

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd apps/backend
uv run pytest ../../tests -q
```

Expected: pytest completes. If failures are unrelated to this MVP, record them in `progress.md` with exact failing test names before continuing.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
cd apps/frontend
npm test
npm run build
```

Expected: Vitest and TypeScript/Vite build pass.

- [ ] **Step 3: Run MCP smoke test**

Run:

```bash
make mcp-smoke
```

Expected: stdio smoke test passes and reports available tools.

- [ ] **Step 4: Add or confirm SSE MCP smoke coverage**

Create `tests/mcp_tests/test_sse_smoke.py` if it does not already exist:

```python
import subprocess
import time
from pathlib import Path

import httpx


def test_mcp_sse_endpoint_starts():
    backend = Path(__file__).resolve().parents[2] / "apps" / "backend"
    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "archivum.mcp.server", "--sse"],
        cwd=backend,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 20
        last_error = None
        while time.time() < deadline:
            try:
                response = httpx.get("http://127.0.0.1:8001/sse", timeout=2)
                if response.status_code in {200, 405}:
                    return
            except Exception as exc:
                last_error = exc
            time.sleep(0.5)
        raise AssertionError(f"MCP SSE endpoint did not start: {last_error}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
```

Run:

```bash
cd apps/backend
uv run pytest ../../tests/mcp_tests/test_sse_smoke.py -q
```

Expected: SSE endpoint starts or the test reveals the exact transport mismatch to fix.

- [ ] **Step 5: Reconcile progress docs**

Update `progress.md` and `docs/project/progress.md` so they agree on:

```markdown
## Current Codebase Status

- Backend API: verified on <date> with `<command>`.
- Frontend: verified on <date> with `<command>`.
- MCP stdio: verified on <date> with `<command>`.
- MCP SSE: verified on <date> with `<command>`.
- Docker boot: verified on <date> with `<command>` or marked not yet verified.
```

- [ ] **Step 6: Commit**

```bash
git add progress.md docs/project/progress.md tests/mcp_tests/test_sse_smoke.py
git commit -m "docs: reconcile second brain mvp progress"
```

---

## Milestone 1: Life OS Data Model

### Task 1.1: Add Life OS Schema And CRUD Helpers

**Files:**
- Modify: `apps/backend/archivum/db/sqlite.py`
- Test: `tests/db/test_life_os.py`

- [x] **Step 1: Write failing DB tests**

Create `tests/db/test_life_os.py`:

```python
import pytest

from archivum.db import sqlite


@pytest.mark.asyncio
async def test_create_project_and_task(temp_settings):
    await sqlite.init_db(temp_settings)

    project = await sqlite.upsert_life_project(
        wiki_id="default",
        key="phoenix",
        name="Phoenix",
        status="active",
        page_slug="project-phoenix",
        summary="Personal knowledge OS MVP",
    )
    task = await sqlite.create_life_task(
        wiki_id="default",
        title="Validate MCP server",
        status="open",
        project_key="phoenix",
        page_slug="project-phoenix",
        source="manual",
    )

    projects = await sqlite.list_life_projects("default")
    tasks = await sqlite.list_life_tasks("default", status="open")

    assert project["key"] == "phoenix"
    assert task["project_key"] == "phoenix"
    assert [p["key"] for p in projects] == ["phoenix"]
    assert [t["title"] for t in tasks] == ["Validate MCP server"]
```

Run:

```bash
cd apps/backend
uv run pytest ../../tests/db/test_life_os.py -q
```

Expected: FAIL because helper functions do not exist.

- [x] **Step 2: Add schema**

Append these tables to `_SCHEMA` in `apps/backend/archivum/db/sqlite.py`:

```sql
CREATE TABLE IF NOT EXISTS life_projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id     TEXT NOT NULL DEFAULT 'default',
    key         TEXT NOT NULL,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    page_slug   TEXT,
    summary     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(wiki_id, key)
);

CREATE TABLE IF NOT EXISTS life_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id     TEXT NOT NULL DEFAULT 'default',
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    project_key TEXT,
    page_slug   TEXT,
    due_date    TEXT,
    source      TEXT NOT NULL DEFAULT 'manual',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS life_decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id     TEXT NOT NULL DEFAULT 'default',
    title       TEXT NOT NULL,
    decision    TEXT NOT NULL,
    rationale   TEXT NOT NULL DEFAULT '',
    project_key TEXT,
    page_slug   TEXT,
    decided_at  TEXT NOT NULL DEFAULT (datetime('now')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS life_people (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id     TEXT NOT NULL DEFAULT 'default',
    name        TEXT NOT NULL,
    page_slug   TEXT,
    summary     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(wiki_id, name)
);

CREATE TABLE IF NOT EXISTS life_areas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id     TEXT NOT NULL DEFAULT 'default',
    key         TEXT NOT NULL,
    name        TEXT NOT NULL,
    page_slug   TEXT,
    summary     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(wiki_id, key)
);

CREATE TABLE IF NOT EXISTS agent_activity (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id     TEXT NOT NULL DEFAULT 'default',
    actor       TEXT NOT NULL DEFAULT 'agent',
    action      TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id   TEXT,
    summary     TEXT NOT NULL DEFAULT '',
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_life_tasks_status ON life_tasks(wiki_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_activity_created ON agent_activity(wiki_id, created_at);
```

- [x] **Step 3: Add minimal helper functions**

Add these functions to `apps/backend/archivum/db/sqlite.py`:

```python
async def upsert_life_project(
    wiki_id: str,
    key: str,
    name: str,
    status: str = "active",
    page_slug: str | None = None,
    summary: str = "",
) -> dict[str, Any]:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO life_projects (wiki_id, key, name, status, page_slug, summary)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(wiki_id, key) DO UPDATE SET
                name=excluded.name,
                status=excluded.status,
                page_slug=excluded.page_slug,
                summary=excluded.summary,
                updated_at=datetime('now')
            """,
            (wiki_id, key, name, status, page_slug, summary),
        )
        await db.commit()
    projects = await list_life_projects(wiki_id)
    return next(p for p in projects if p["key"] == key)


async def list_life_projects(wiki_id: str = "default") -> list[dict[str, Any]]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM life_projects WHERE wiki_id=? ORDER BY updated_at DESC",
            (wiki_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def create_life_task(
    wiki_id: str,
    title: str,
    status: str = "open",
    project_key: str | None = None,
    page_slug: str | None = None,
    due_date: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    async with get_db() as db:
        cur = await db.execute(
            """
            INSERT INTO life_tasks (wiki_id, title, status, project_key, page_slug, due_date, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (wiki_id, title, status, project_key, page_slug, due_date, source),
        )
        await db.commit()
        task_id = cur.lastrowid
        async with db.execute("SELECT * FROM life_tasks WHERE id=?", (task_id,)) as row_cur:
            row = await row_cur.fetchone()
            return dict(row)


async def list_life_tasks(wiki_id: str = "default", status: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM life_tasks WHERE wiki_id=?"
    args: list[Any] = [wiki_id]
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY updated_at DESC"
    async with get_db() as db:
        async with db.execute(sql, args) as cur:
            return [dict(r) for r in await cur.fetchall()]
```

- [x] **Step 4: Run test**

```bash
cd apps/backend
uv run pytest ../../tests/db/test_life_os.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/db/sqlite.py tests/db/test_life_os.py
git commit -m "feat: add life os storage"
```

---

## Milestone 2: Life OS Service And API

### Task 2.1: Build Daily Notes And Project Registry Service

**Files:**
- Create: `apps/backend/archivum/life_os/models.py`
- Create: `apps/backend/archivum/life_os/service.py`
- Create: `apps/backend/archivum/life_os/__init__.py`
- Test: `tests/test_life_os_service.py`

- [x] **Step 1: Write failing service tests**

Create `tests/test_life_os_service.py`:

```python
import pytest

from archivum.db import sqlite
from archivum.life_os.service import ensure_daily_note, register_project


@pytest.mark.asyncio
async def test_ensure_daily_note_creates_portable_markdown(temp_settings):
    await sqlite.init_db(temp_settings)

    page = await ensure_daily_note("2026-06-21", wiki_id="default")

    assert page["slug"] == "daily-2026-06-21"
    assert "type: daily" in page["content"]
    assert "## Log" in page["content"]
    assert "## Tasks" in page["content"]


@pytest.mark.asyncio
async def test_register_project_creates_project_page_and_row(temp_settings):
    await sqlite.init_db(temp_settings)

    project = await register_project(
        key="phoenix",
        name="Phoenix",
        summary="Second-brain MVP",
        wiki_id="default",
    )

    page = await sqlite.get_page("project-phoenix", "default")
    projects = await sqlite.list_life_projects("default")

    assert project["page_slug"] == "project-phoenix"
    assert page is not None
    assert "type: project" in page["content"]
    assert projects[0]["key"] == "phoenix"
```

Run:

```bash
cd apps/backend
uv run pytest ../../tests/test_life_os_service.py -q
```

Expected: FAIL because service module does not exist.

- [x] **Step 2: Add models**

Create `apps/backend/archivum/life_os/models.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectInput(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str = ""
    status: str = "active"


class TaskInput(BaseModel):
    title: str = Field(min_length=1)
    project_key: str | None = None
    page_slug: str | None = None
    due_date: str | None = None
    source: str = "manual"


class DecisionInput(BaseModel):
    title: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    rationale: str = ""
    project_key: str | None = None
    page_slug: str | None = None
```

Create `apps/backend/archivum/life_os/__init__.py`:

```python
"""Life OS workflows for daily notes, projects, tasks, decisions, and activity."""
```

- [x] **Step 3: Add service**

Create `apps/backend/archivum/life_os/service.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime

from archivum.db import qdrant_client as qdrant, sqlite
from archivum.ingest.agent import slugify
from archivum.config import get_settings


def _frontmatter(kind: str, **fields: str) -> str:
    lines = ["---", f"type: {kind}"]
    for key, value in fields.items():
        if value:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


async def ensure_daily_note(day: str | None = None, wiki_id: str = "default") -> dict:
    day = day or date.today().isoformat()
    slug = f"daily-{day}"
    existing = await sqlite.get_page(slug, wiki_id)
    if existing:
        return existing
    title = f"Daily Note {day}"
    content = f"""{_frontmatter("daily", date=day)}

# {title}

## Log

## Tasks

## Decisions

## Links
"""
    await sqlite.upsert_page(slug, title, content, ["daily"], "user", wiki_id)
    await qdrant.upsert_page(slug, title, content, wiki_id, get_settings())
    return await sqlite.get_page(slug, wiki_id)


async def register_project(
    key: str,
    name: str,
    summary: str = "",
    status: str = "active",
    wiki_id: str = "default",
) -> dict:
    project_key = slugify(key)
    slug = f"project-{project_key}"
    title = name
    content = f"""{_frontmatter("project", project_key=project_key, status=status)}

# {name}

{summary}

## Outcomes

## Current Work

## Decisions

## Tasks

## Links
"""
    await sqlite.upsert_page(slug, title, content, ["project"], "user", wiki_id)
    await qdrant.upsert_page(slug, title, content, wiki_id, get_settings())
    return await sqlite.upsert_life_project(wiki_id, project_key, name, status, slug, summary)
```

- [x] **Step 4: Run service tests**

```bash
cd apps/backend
uv run pytest ../../tests/test_life_os_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/life_os tests/test_life_os_service.py
git commit -m "feat: add life os service"
```

### Task 2.2: Add REST API For Life OS

**Files:**
- Create: `apps/backend/archivum/api/life_os.py`
- Modify: `apps/backend/archivum/main.py`
- Test: `tests/api/test_life_os_api.py`

- [x] **Step 1: Write failing API tests**

Create `tests/api/test_life_os_api.py`:

```python
def test_daily_note_endpoint(auth_client):
    response = auth_client.post("/api/life/daily", json={"date": "2026-06-21"})
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "daily-2026-06-21"


def test_project_endpoint(auth_client):
    response = auth_client.post(
        "/api/life/projects",
        json={"key": "phoenix", "name": "Phoenix", "summary": "Second brain MVP"},
    )
    assert response.status_code == 200
    assert response.json()["key"] == "phoenix"

    list_response = auth_client.get("/api/life/projects")
    assert list_response.status_code == 200
    assert list_response.json()[0]["key"] == "phoenix"
```

Run:

```bash
cd apps/backend
uv run pytest ../../tests/api/test_life_os_api.py -q
```

Expected: FAIL with 404.

- [x] **Step 2: Add router**

Create `apps/backend/archivum/api/life_os.py`:

```python
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends

from archivum.api.auth import require_writer
from archivum.db import sqlite
from archivum.life_os.models import ProjectInput, TaskInput
from archivum.life_os.service import ensure_daily_note, register_project

router = APIRouter(prefix="/api/life", tags=["life-os"])


class DailyInput(BaseModel):
    date: str | None = None


@router.post("/daily")
async def create_daily_note(payload: DailyInput, _user=Depends(require_writer)):
    return await ensure_daily_note(payload.date, wiki_id="default")


@router.post("/projects")
async def create_project(payload: ProjectInput, _user=Depends(require_writer)):
    return await register_project(
        key=payload.key,
        name=payload.name,
        summary=payload.summary,
        status=payload.status,
        wiki_id="default",
    )


@router.get("/projects")
async def list_projects(_user=Depends(require_writer)):
    return await sqlite.list_life_projects("default")


@router.post("/tasks")
async def create_task(payload: TaskInput, _user=Depends(require_writer)):
    return await sqlite.create_life_task(
        wiki_id="default",
        title=payload.title,
        project_key=payload.project_key,
        page_slug=payload.page_slug,
        due_date=payload.due_date,
        source=payload.source,
    )


@router.get("/tasks")
async def list_tasks(status: str | None = None, _user=Depends(require_writer)):
    return await sqlite.list_life_tasks("default", status=status)
```

- [x] **Step 3: Mount router**

In `apps/backend/archivum/main.py`, import and include the router:

```python
from archivum.api import life_os

app.include_router(life_os.router)
```

- [x] **Step 4: Run API tests**

```bash
cd apps/backend
uv run pytest ../../tests/api/test_life_os_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/api/life_os.py apps/backend/archivum/main.py tests/api/test_life_os_api.py
git commit -m "feat: expose life os api"
```

---

## Milestone 3: MCP Tools For Personal Knowledge Workflows

### Task 3.1: Add Life OS MCP Tools

**Files:**
- Modify: `apps/backend/archivum/mcp/server.py`
- Test: `tests/mcp_tests/test_server.py`

- [x] **Step 1: Write failing MCP tests**

Add tests that call tool functions directly:

```python
import pytest

from archivum.db import sqlite
from archivum.mcp import server


@pytest.mark.asyncio
async def test_mcp_life_os_tools(temp_settings, monkeypatch):
    monkeypatch.setattr(server, "settings", temp_settings)
    await sqlite.init_db(temp_settings)

    daily = await server.life_daily_note("2026-06-21")
    project = await server.life_register_project("phoenix", "Phoenix", "MVP")
    task = await server.life_create_task("Wire Life OS MCP", project_key="phoenix")

    assert daily["slug"] == "daily-2026-06-21"
    assert project["key"] == "phoenix"
    assert task["project_key"] == "phoenix"
```

Run:

```bash
cd apps/backend
uv run pytest ../../tests/mcp_tests/test_server.py -q
```

Expected: FAIL because MCP functions do not exist.

- [x] **Step 2: Add MCP tools**

Append to `apps/backend/archivum/mcp/server.py`:

```python
from archivum.life_os.service import ensure_daily_note, register_project


@mcp.tool()
async def life_daily_note(day: str | None = None, wiki_id: str = "default") -> dict[str, Any]:
    """Create or return the daily note for YYYY-MM-DD."""
    _require_key()
    set_trace_id(new_trace_id("mcp-life-daily"))
    return await ensure_daily_note(day, wiki_id=wiki_id)


@mcp.tool()
async def life_register_project(
    key: str,
    name: str,
    summary: str = "",
    status: str = "active",
    wiki_id: str = "default",
) -> dict[str, Any]:
    """Register a project and create its canonical project page."""
    _require_key()
    set_trace_id(new_trace_id("mcp-life-project"))
    return await register_project(key, name, summary, status, wiki_id)


@mcp.tool()
async def life_create_task(
    title: str,
    project_key: str | None = None,
    page_slug: str | None = None,
    due_date: str | None = None,
    wiki_id: str = "default",
) -> dict[str, Any]:
    """Create a Life OS task linked to an optional project or page."""
    _require_key()
    set_trace_id(new_trace_id("mcp-life-task"))
    return await sqlite.create_life_task(
        wiki_id=wiki_id,
        title=title,
        project_key=project_key,
        page_slug=page_slug,
        due_date=due_date,
        source="mcp",
    )
```

- [x] **Step 3: Run MCP tests**

```bash
cd apps/backend
uv run pytest ../../tests/mcp_tests/test_server.py -q
```

Expected: PASS.

- [x] **Step 4: Verify tool listing**

Run:

```bash
make mcp-smoke
```

Expected: output includes `life_daily_note`, `life_register_project`, and `life_create_task`.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/mcp/server.py tests/mcp_tests/test_server.py
git commit -m "feat: add life os mcp tools"
```

---

## Milestone 4: Obsidian-Like Daily Interface

### Task 4.1: Add Frontend Types And API Client

**Files:**
- Modify: `apps/frontend/src/types.ts`
- Modify: `apps/frontend/src/api.ts`
- Test: `apps/frontend/src/api.test.ts`

- [ ] **Step 1: Add frontend types**

Add to `apps/frontend/src/types.ts`:

```ts
export type LifeProject = {
  id: number;
  key: string;
  name: string;
  status: string;
  page_slug?: string | null;
  summary: string;
  updated_at: string;
};

export type LifeTask = {
  id: number;
  title: string;
  status: string;
  project_key?: string | null;
  page_slug?: string | null;
  due_date?: string | null;
  source: string;
  updated_at: string;
};
```

- [ ] **Step 2: Add API methods**

Add to `apps/frontend/src/api.ts`:

```ts
import type { LifeProject, LifeTask } from './types';

export async function ensureDailyNote(date?: string): Promise<Page> {
  return request('/api/life/daily', {
    method: 'POST',
    body: JSON.stringify({ date }),
  });
}

export async function listLifeProjects(): Promise<LifeProject[]> {
  return request('/api/life/projects');
}

export async function createLifeProject(input: { key: string; name: string; summary?: string; status?: string }): Promise<LifeProject> {
  return request('/api/life/projects', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function listLifeTasks(status?: string): Promise<LifeTask[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return request(`/api/life/tasks${qs}`);
}

export async function createLifeTask(input: { title: string; project_key?: string; page_slug?: string; due_date?: string }): Promise<LifeTask> {
  return request('/api/life/tasks', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}
```

- [ ] **Step 3: Add API tests**

Extend `apps/frontend/src/api.test.ts` with mocked fetch assertions for `ensureDailyNote`, `listLifeProjects`, and `createLifeTask`.

- [ ] **Step 4: Run frontend tests**

```bash
cd apps/frontend
npm test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/types.ts apps/frontend/src/api.ts apps/frontend/src/api.test.ts
git commit -m "feat: add life os frontend api"
```

### Task 4.2: Add Daily, Projects, Tasks, Decisions, And Activity Pages

**Files:**
- Modify: `apps/frontend/src/App.tsx`
- Modify: `apps/frontend/src/components/Layout.tsx`
- Create: `apps/frontend/src/pages/DailyPage.tsx`
- Create: `apps/frontend/src/pages/ProjectsPage.tsx`
- Create: `apps/frontend/src/pages/TasksPage.tsx`
- Create: `apps/frontend/src/pages/DecisionsPage.tsx`
- Create: `apps/frontend/src/pages/ActivityPage.tsx`

- [ ] **Step 1: Create `DailyPage.tsx`**

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ensureDailyNote } from '../api';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';

export default function DailyPage() {
  const navigate = useNavigate();
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);

  async function openDaily() {
    setLoading(true);
    try {
      const page = await ensureDailyNote(date);
      navigate(`/wiki/${page.slug}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-4 max-w-2xl space-y-3">
      <div className="flex items-center gap-2">
        <Input value={date} onChange={(event) => setDate(event.target.value)} type="date" className="max-w-48" />
        <Button onClick={openDaily} disabled={loading}>{loading ? 'Opening...' : 'Open daily note'}</Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `ProjectsPage.tsx`**

Implement a compact list and creation form using `listLifeProjects` and `createLifeProject`. On clicking a project, navigate to `/wiki/${project.page_slug}`.

- [ ] **Step 3: Create `TasksPage.tsx`**

Implement an open task list and one-line capture form using `listLifeTasks('open')` and `createLifeTask`.

- [ ] **Step 4: Create placeholder-backed `DecisionsPage.tsx` and `ActivityPage.tsx`**

Use the same page shell and make them call their API methods once those are added in Milestone 5. Until then, show an empty state driven by an empty array, not static explanatory copy.

- [ ] **Step 5: Add routes**

In `apps/frontend/src/App.tsx`, import pages and add protected routes:

```tsx
<Route path="/daily" element={<Layout><DailyPage /></Layout>} />
<Route path="/projects" element={<Layout><ProjectsPage /></Layout>} />
<Route path="/tasks" element={<Layout><TasksPage /></Layout>} />
<Route path="/decisions" element={<Layout><DecisionsPage /></Layout>} />
<Route path="/activity" element={<Layout><ActivityPage /></Layout>} />
```

- [ ] **Step 6: Add navigation**

In `apps/frontend/src/components/Layout.tsx`, add nav items:

```ts
{ label: 'Daily', path: '/daily', view: 'daily' },
{ label: 'Projects', path: '/projects', view: 'projects' },
{ label: 'Tasks', path: '/tasks', view: 'tasks' },
{ label: 'Decisions', path: '/decisions', view: 'decisions' },
{ label: 'Activity', path: '/activity', view: 'activity' },
```

Update the `NavItem['view']` union to include those values.

- [ ] **Step 7: Run build**

```bash
cd apps/frontend
npm run build
```

Expected: PASS and no TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add apps/frontend/src/App.tsx apps/frontend/src/components/Layout.tsx apps/frontend/src/pages
git commit -m "feat: add second brain workspace pages"
```

---

## Milestone 5: Decisions, Activity, And Provenance

### Task 5.1: Add Decision And Activity Helpers, API, And MCP

**Files:**
- Modify: `apps/backend/archivum/db/sqlite.py`
- Modify: `apps/backend/archivum/life_os/service.py`
- Modify: `apps/backend/archivum/api/life_os.py`
- Modify: `apps/backend/archivum/mcp/server.py`
- Test: `tests/api/test_life_os_api.py`
- Test: `tests/mcp_tests/test_server.py`

- [ ] **Step 1: Add DB helpers**

Add:

```python
async def create_life_decision(
    wiki_id: str,
    title: str,
    decision: str,
    rationale: str = "",
    project_key: str | None = None,
    page_slug: str | None = None,
) -> dict[str, Any]:
    async with get_db() as db:
        cur = await db.execute(
            """
            INSERT INTO life_decisions (wiki_id, title, decision, rationale, project_key, page_slug)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (wiki_id, title, decision, rationale, project_key, page_slug),
        )
        await db.commit()
        async with db.execute("SELECT * FROM life_decisions WHERE id=?", (cur.lastrowid,)) as row_cur:
            row = await row_cur.fetchone()
            return dict(row)


async def list_life_decisions(wiki_id: str = "default") -> list[dict[str, Any]]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM life_decisions WHERE wiki_id=? ORDER BY decided_at DESC",
            (wiki_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def log_agent_activity(
    wiki_id: str,
    actor: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with get_db() as db:
        cur = await db.execute(
            """
            INSERT INTO agent_activity (wiki_id, actor, action, target_type, target_id, summary, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (wiki_id, actor, action, target_type, target_id, summary, json.dumps(metadata or {})),
        )
        await db.commit()
        async with db.execute("SELECT * FROM agent_activity WHERE id=?", (cur.lastrowid,)) as row_cur:
            row = await row_cur.fetchone()
            return dict(row)


async def list_agent_activity(wiki_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM agent_activity WHERE wiki_id=? ORDER BY created_at DESC LIMIT ?",
            (wiki_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
```

- [ ] **Step 2: Log activity in existing MCP write paths**

In `write_page`, after graph indexing:

```python
await sqlite.log_agent_activity(
    wiki_id=wiki_id,
    actor="mcp",
    action="write_page",
    target_type="page",
    target_id=final_slug,
    summary=f"Wrote page {title}",
)
```

Add similar logs in `ingest_source`, `life_register_project`, `life_create_task`, and `life_daily_note`.

- [ ] **Step 3: Add API endpoints**

Add to `api/life_os.py`:

```python
@router.post("/decisions")
async def create_decision(payload: DecisionInput, _user=Depends(require_writer)):
    return await sqlite.create_life_decision(
        wiki_id="default",
        title=payload.title,
        decision=payload.decision,
        rationale=payload.rationale,
        project_key=payload.project_key,
        page_slug=payload.page_slug,
    )


@router.get("/decisions")
async def list_decisions(_user=Depends(require_writer)):
    return await sqlite.list_life_decisions("default")


@router.get("/activity")
async def list_activity(_user=Depends(require_writer)):
    return await sqlite.list_agent_activity("default")
```

- [ ] **Step 4: Add MCP decision and activity tools**

```python
@mcp.tool()
async def life_record_decision(
    title: str,
    decision: str,
    rationale: str = "",
    project_key: str | None = None,
    page_slug: str | None = None,
    wiki_id: str = "default",
) -> dict[str, Any]:
    """Record a decision in the Life OS decision log."""
    _require_key()
    result = await sqlite.create_life_decision(wiki_id, title, decision, rationale, project_key, page_slug)
    await sqlite.log_agent_activity(wiki_id, "mcp", "record_decision", "decision", str(result["id"]), title)
    return result


@mcp.tool()
async def life_activity(limit: int = 50, wiki_id: str = "default") -> list[dict[str, Any]]:
    """Return recent agent and system activity."""
    _require_key()
    return await sqlite.list_agent_activity(wiki_id, limit)
```

- [ ] **Step 5: Run tests**

```bash
cd apps/backend
uv run pytest ../../tests/api/test_life_os_api.py ../../tests/mcp_tests/test_server.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/db/sqlite.py apps/backend/archivum/api/life_os.py apps/backend/archivum/mcp/server.py tests/api/test_life_os_api.py tests/mcp_tests/test_server.py
git commit -m "feat: track life os decisions and agent activity"
```

---

## Milestone 6: Hybrid Search And Review Workflows

### Task 6.1: Confirm Or Add Hybrid Search

**Files:**
- Modify: `apps/backend/archivum/db/sqlite.py`
- Modify: `apps/backend/archivum/api/search.py`
- Modify: `apps/backend/archivum/mcp/server.py`
- Test: `tests/api/test_search.py`

- [ ] **Step 1: Add failing hybrid search test**

Add:

```python
def test_search_includes_exact_keyword_hits(auth_client):
    auth_client.post("/api/pages", json={
        "title": "Project Phoenix",
        "content": "The unique marker is hyperion-capsule.",
        "tags": ["project"],
    })

    response = auth_client.get("/api/search", params={"q": "hyperion-capsule"})

    assert response.status_code == 200
    body = response.json()
    assert any(hit["slug"] == "project-phoenix" for hit in body["results"])
    assert any(hit.get("source") in {"keyword", "hybrid"} for hit in body["results"])
```

- [ ] **Step 2: Add FTS helper**

Add `keyword_search_pages(query, wiki_id, limit)` in `sqlite.py` using `pages_fts MATCH ?`.

- [ ] **Step 3: Merge semantic and keyword results**

In `api/search.py`, return a normalized result list that includes:

```python
{
    "slug": slug,
    "title": title,
    "excerpt": excerpt,
    "score": score,
    "source": "semantic" | "keyword" | "hybrid",
}
```

- [ ] **Step 4: Update MCP `search_wiki`**

Return hybrid results from the same shared helper instead of only Qdrant results.

- [ ] **Step 5: Run search tests**

```bash
cd apps/backend
uv run pytest ../../tests/api/test_search.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/db/sqlite.py apps/backend/archivum/api/search.py apps/backend/archivum/mcp/server.py tests/api/test_search.py
git commit -m "feat: add hybrid second brain search"
```

---

## Milestone 7: Import, Export, Backup, And Project Connections

### Task 7.1: Add Obsidian-Compatible Vault Export

**Files:**
- Modify: `apps/backend/archivum/api/export.py`
- Test: `tests/api/test_export.py`

- [ ] **Step 1: Add export test**

Add a test that creates two pages and downloads `/api/export/obsidian`, then asserts the zip contains `pages/<slug>.md` and an `archivum-manifest.json`.

- [ ] **Step 2: Implement zip export**

Use Python `zipfile` to write:

```text
pages/<slug>.md
archivum-manifest.json
```

The manifest should contain page count, export timestamp, and Life OS table counts.

- [ ] **Step 3: Run export tests**

```bash
cd apps/backend
uv run pytest ../../tests/api/test_export.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/archivum/api/export.py tests/api/test_export.py
git commit -m "feat: export obsidian compatible vault"
```

### Task 7.2: Add Explicit Project Registration For Local Repos

**Files:**
- Modify: `apps/backend/archivum/life_os/models.py`
- Modify: `apps/backend/archivum/life_os/service.py`
- Modify: `apps/backend/archivum/api/life_os.py`
- Modify: `apps/backend/archivum/mcp/server.py`

- [ ] **Step 1: Add `local_path` to project registration**

Add optional `local_path: str | None = None` to `ProjectInput`, `register_project`, and `life_register_project`.

- [ ] **Step 2: Store path in project page frontmatter**

Only store the path if explicitly provided:

```yaml
local_path: /Users/kitts/path/to/project
```

- [ ] **Step 3: Do not crawl automatically**

Project registration must not recursively scan the path. Add a button or MCP tool argument later for explicit ingest.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/archivum/life_os apps/backend/archivum/api/life_os.py apps/backend/archivum/mcp/server.py
git commit -m "feat: register local project context"
```

---

## Milestone 8: Documentation And Operating Manual

### Task 8.1: Document Life OS Conventions

**Files:**
- Create: `docs/project/life-os-conventions.md`
- Modify: `README.md`
- Modify: `progress.md`

- [ ] **Step 1: Create conventions doc**

Write `docs/project/life-os-conventions.md` with these sections:

```markdown
# Life OS Conventions

## Page Types

- `daily`: `daily-YYYY-MM-DD`
- `project`: `project-<key>`
- `area`: `area-<key>`
- `person`: `person-<slug>`
- `decision`: logged in SQLite and optionally linked from project pages
- `source`: generated by ingest

## Agent Write Rules

- Prefer MCP tools over direct file edits.
- Use `life_register_project` before writing project memory.
- Use `life_record_decision` for architectural or personal workflow decisions.
- Use `life_create_task` for actionable work.
- Use `write_page` only when updating canonical markdown content.

## Review Loop

- Start day from `/daily`.
- Capture inbox items as tasks.
- Link project work to `project-<key>`.
- Record decisions when a path is chosen.
- Run lint weekly.
- Export vault before major migrations.
```

- [ ] **Step 2: Update README**

Add:

```markdown
## Personal Second-Brain Setup

1. Run `./install.sh` or `make setup`.
2. Configure `.env`.
3. Start with `make up`.
4. Open the web UI.
5. Connect your MCP client with `make print-mcp-config`.
6. Create your first daily note from `/daily`.
7. Register active projects from `/projects` or via `life_register_project`.
```

- [ ] **Step 3: Update progress**

Mark completed tasks and remaining verification gaps in `progress.md`.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/project/life-os-conventions.md progress.md
git commit -m "docs: add second brain operating guide"
```

---

## Milestone 9: End-To-End Verification

### Task 9.1: Verify MVP As A User

**Files:**
- Modify: `progress.md`

- [ ] **Step 1: Run full automated test suite**

```bash
cd apps/backend
uv run pytest ../../tests -q
cd ../frontend
npm test
npm run build
```

Expected: all pass.

- [ ] **Step 2: Boot stack**

```bash
make up
```

Expected: frontend, backend, MCP, Qdrant, and Caddy report healthy.

- [ ] **Step 3: Verify browser flow**

Open the UI and manually verify:

```text
/daily creates today's note
/projects registers Phoenix and opens its page
/tasks creates an open task
/decisions records a decision
/activity shows recent MCP/API activity
/query answers against created pages
/graph shows project and page relationships
```

- [ ] **Step 4: Verify MCP flow**

From an MCP client or inspector, call:

```text
life_daily_note
life_register_project
life_create_task
life_record_decision
search_wiki
query
lint_wiki
```

Expected: each tool returns structured JSON and writes activity where appropriate.

- [ ] **Step 5: Verify export and restore readiness**

Download Obsidian export and confirm markdown files can be opened in a plain editor.

- [ ] **Step 6: Update final progress**

In `progress.md`, add:

```markdown
## Verification

- Backend tests: PASS on <date>
- Frontend tests: PASS on <date>
- Frontend build: PASS on <date>
- Docker boot: PASS on <date>
- MCP stdio: PASS on <date>
- MCP SSE: PASS on <date>
- Manual Life OS flow: PASS on <date>
```

- [ ] **Step 7: Commit**

```bash
git add progress.md
git commit -m "docs: record second brain mvp verification"
```

---

## Scope Guardrails

- Keep the MVP single-user first. Multi-user roles already exist, but do not build collaboration workflows unless needed for personal use.
- Keep markdown portable. SQLite tables accelerate workflows, but every important Life OS object should link to or render as markdown.
- Keep MCP local/private by default. Public write-capable MCP is out of scope for this MVP.
- Do not add automatic recursive filesystem crawling. Project paths are explicit context, and ingestion should be user-initiated.
- Do not build recurring tasks, calendars, mobile apps, plugin ecosystems, or automatic email sync in this MVP.

## Execution Order

1. Milestone 0 gives a reliable baseline.
2. Milestones 1-3 make Life OS agent-addressable.
3. Milestones 4-5 make it usable in the browser.
4. Milestones 6-7 make it useful for retrieval, project context, and portability.
5. Milestones 8-9 make it operable as a personal system.

## Self-Review

- Spec coverage: The plan covers MCP, Obsidian-like UI, personal knowledge storage, Life OS workflows, project registry, activity/provenance, import/export, documentation, and verification.
- Placeholder scan: The plan avoids open-ended implementation placeholders; remaining design choices are scoped as explicit guardrails.
- Type consistency: Project keys use `key`/`project_key`, pages use `slug`/`page_slug`, Life OS API paths live under `/api/life`, and MCP tools use the `life_` prefix.
