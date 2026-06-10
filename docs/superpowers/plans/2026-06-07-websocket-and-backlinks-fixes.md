# WebSocket Progress & Backlinks 404 Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the WebSocket ingest-progress connection that silently breaks upload progress indicators, and fix the backlinks endpoint that returns 404 on all real slugs.

**Architecture:** Two independent bugs. (1) The Caddy reverse proxy at `caddy/Caddyfile` routes `/api/*` without WebSocket upgrade headers, so the browser's WS handshake is silently dropped; separately, Vite's dev proxy config also lacks `ws: true`. (2) FastAPI matches routes top-to-bottom; `GET /{slug:path}` is defined before `GET /{slug:path}/backlinks`, so `compute-blade/backlinks` is parsed as a page slug rather than a special sub-route, causing a guaranteed 404.

**Tech Stack:** Python/FastAPI (backend), TypeScript/React + Vite (frontend), Caddy (reverse proxy), Docker Compose

---

## File Map

| File | Change |
|------|--------|
| `caddy/Caddyfile` | Add a specific `/api/ingest/ws` handler with WebSocket upgrade headers before the generic `/api/*` block |
| `apps/frontend/vite.config.ts` | Change `/api` proxy from string shorthand to object form with `ws: true` |
| `apps/backend/archivum/api/pages.py` | Move `get_backlinks` route decorator + function **above** `get_page` |
| `tests/test_pages_backlinks.py` | New test: verify backlinks route is hit (not shadowed by `get_page`) |
| `tests/test_ingest_websocket.py` | Existing file — extend with a test that auth rejection closes code 1008 |

---

## Task 1: Fix Caddy WebSocket routing

**Files:**
- Modify: `caddy/Caddyfile`

The `/api/*` block does not include `header_up Upgrade websocket` / `header_up Connection Upgrade`, so Caddy silently forwards the request as plain HTTP and the backend never receives a WS handshake. Adding a more-specific `handle /api/ingest/ws` block *before* the generic `/api/*` block fixes this because Caddy matches in declaration order.

- [ ] **Step 1: Read the current Caddyfile**

```
caddy/Caddyfile
```

Expected: the file starts with a `handle /api/* { reverse_proxy backend:8000 }` block (no upgrade headers) followed by a `handle /ws/* { … }` block that *does* have them.

- [ ] **Step 2: Insert a dedicated WebSocket handler before the `/api/*` block**

Replace the existing production vhost block so it reads:

```caddy
{
	email pranav.kannepalli@gmail.com
}

# ─── Production (ARCHIVUM_HOST set) ──────────────────────────────────────────
{$ARCHIVUM_HOST:localhost} {
	# WebSocket for ingest progress — must come before /api/* to get upgrade headers
	handle /api/ingest/ws {
		reverse_proxy backend:8000 {
			header_up Upgrade websocket
			header_up Connection Upgrade
		}
	}

	# Proxy API to backend
	handle /api/* {
		reverse_proxy backend:8000
	}

	# WebSocket for editor auto-save
	handle /ws/* {
		reverse_proxy backend:8000 {
			header_up Upgrade websocket
			header_up Connection Upgrade
		}
	}

	# Serve frontend
	handle {
		reverse_proxy frontend:8080
	}

	# Security headers
	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options nosniff
		X-Frame-Options DENY
		Referrer-Policy strict-origin-when-cross-origin
		Content-Security-Policy "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ws: wss:; font-src 'self'"
	}

	encode gzip
}
```

(Leave the `share.{$ARCHIVUM_HOST}` block untouched — it doesn't have any WS routes.)

- [ ] **Step 3: Commit**

```bash
git add caddy/Caddyfile
git commit -m "fix: add WebSocket upgrade headers for /api/ingest/ws in Caddy"
```

---

## Task 2: Fix Vite dev-mode WebSocket proxy

**Files:**
- Modify: `apps/frontend/vite.config.ts`

Vite's string-shorthand proxy (`'/api': 'http://localhost:8000'`) only proxies HTTP. WebSocket connections require the object form with `ws: true`.

- [ ] **Step 1: Read the current vite.config.ts**

```
apps/frontend/vite.config.ts
```

Expected: `proxy: { '/api': 'http://localhost:8000' }`

- [ ] **Step 2: Change the proxy entry to enable WebSocket**

```typescript
server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        ws: true,
      },
    },
  },
```

- [ ] **Step 3: Verify TypeScript still compiles**

```bash
cd apps/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/vite.config.ts
git commit -m "fix: enable WebSocket proxying in Vite dev server for /api"
```

---

## Task 3: Fix FastAPI route ordering for backlinks

**Files:**
- Modify: `apps/backend/archivum/api/pages.py`

FastAPI matches routes in registration order. `GET /{slug:path}` is registered at line 137; `GET /{slug:path}/backlinks` is registered at line 286. Because the `path` converter matches `/`, a GET request to `/api/pages/compute-blade/backlinks` is swallowed by the first route with `slug = "compute-blade/backlinks"`, which then fails the `sqlite.get_page()` lookup.

The fix is to move the `get_backlinks` handler to be defined *before* `get_page`.

- [ ] **Step 1: Read the route section of pages.py**

Read lines 128–300 of `apps/backend/archivum/api/pages.py` to confirm the ordering.

Expected: `@router.get("/{slug:path}")` at ~line 137, `@router.get("/{slug:path}/backlinks")` at ~line 286.

- [ ] **Step 2: Move get_backlinks above get_page**

Cut the entire `get_backlinks` function (decorator + body, currently lines 286–299) and paste it **immediately before** the `@router.get("/{slug:path}")` decorator that opens `get_page`. The result should look like:

```python
@router.get("/{slug:path}/backlinks", response_model=list[dict])
async def get_backlinks(
    slug: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    slug = _validate_slug(slug)
    existing = await sqlite.get_page(slug, current_user.wiki_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Page '{slug}' not found", "code": "page_not_found"},
        )
    return await graph.get_backlinks(slug, current_user.wiki_id)


@router.get("/{slug:path}", response_model=PageDetail)
async def get_page(
    ...
```

Do not change any logic inside either function — only the order.

- [ ] **Step 3: Write a failing test first**

Create `tests/test_pages_backlinks.py`:

```python
"""Regression test: GET /{slug}/backlinks must not be shadowed by GET /{slug:path}."""

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.main import create_app


class BacklinksRouteTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.token = create_access_token("owner", "owner", "default", self.settings)
        self.app = create_app()
        self.client = TestClient(self.app)
        self.client.cookies.set("access_token", self.token)

    def test_backlinks_route_not_shadowed_by_slug_catch_all(self):
        """GET /api/pages/my-page/backlinks must return backlinks, not 404."""
        fake_page = {
            "id": 1,
            "slug": "my-page",
            "title": "My Page",
            "content": "",
            "tags": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "authored_by": "owner",
        }
        fake_backlinks = [{"slug": "other-page", "title": "Other Page"}]

        with (
            patch(
                "archivum.api.pages.sqlite.get_page",
                new=AsyncMock(return_value=fake_page),
            ),
            patch(
                "archivum.api.pages.graph.get_backlinks",
                new=AsyncMock(return_value=fake_backlinks),
            ),
        ):
            response = self.client.get("/api/pages/my-page/backlinks")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["slug"], "other-page")

    def test_backlinks_returns_404_when_page_missing(self):
        """Backlinks for a non-existent page should return 404 with page_not_found."""
        with patch(
            "archivum.api.pages.sqlite.get_page",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.get("/api/pages/ghost-page/backlinks")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "page_not_found")

    def test_nested_slug_backlinks(self):
        """GET /api/pages/compute-blade/backlinks must parse slug as 'compute-blade'."""
        fake_page = {
            "id": 2,
            "slug": "compute-blade",
            "title": "Compute Blade",
            "content": "",
            "tags": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "authored_by": "owner",
        }

        with (
            patch(
                "archivum.api.pages.sqlite.get_page",
                new=AsyncMock(return_value=fake_page),
            ) as mock_get_page,
            patch(
                "archivum.api.pages.graph.get_backlinks",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = self.client.get("/api/pages/compute-blade/backlinks")

        self.assertEqual(response.status_code, 200)
        # Verify the slug passed to sqlite was "compute-blade", not "compute-blade/backlinks"
        mock_get_page.assert_called_once_with("compute-blade", "default")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run test to confirm it fails before the fix**

```bash
cd apps/backend && python -m pytest ../../tests/test_pages_backlinks.py -v
```

Expected: `test_backlinks_route_not_shadowed_by_slug_catch_all` FAILS with status 404 (the route is being swallowed by `get_page`).

- [ ] **Step 5: Apply the route reorder from Step 2**

(Move `get_backlinks` above `get_page` as described.)

- [ ] **Step 6: Run tests to confirm they pass**

```bash
cd apps/backend && python -m pytest ../../tests/test_pages_backlinks.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 7: Run the full test suite to check for regressions**

```bash
cd apps/backend && python -m pytest ../../tests/ -v
```

Expected: all existing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add apps/backend/archivum/api/pages.py tests/test_pages_backlinks.py
git commit -m "fix: move backlinks route before slug catch-all to prevent 404 shadowing"
```

---

## Task 4: Verify WebSocket auth rejection still works (guard regression)

**Files:**
- Modify: `tests/test_ingest_websocket.py`

The existing test only covers the happy path. Adding an unauthenticated-connection test guards against accidentally removing the 1008 close.

- [ ] **Step 1: Read the existing test file**

```
tests/test_ingest_websocket.py
```

- [ ] **Step 2: Add an unauthenticated rejection test**

Append to the `IngestWebSocketTests` class:

```python
    def test_ingest_websocket_rejects_unauthenticated(self):
        app = create_app()
        client = TestClient(app)
        # No cookie set — connection should be closed with code 1008
        with self.assertRaises(Exception):
            with client.websocket_connect("/api/ingest/ws") as ws:
                ws.receive_json()  # Should never reach here
```

(FastAPI's `TestClient` raises when the server closes with a non-normal code, so `assertRaises(Exception)` is the idiomatic check here.)

- [ ] **Step 3: Run the WebSocket tests**

```bash
cd apps/backend && python -m pytest ../../tests/test_ingest_websocket.py -v
```

Expected: both tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ingest_websocket.py
git commit -m "test: add unauthenticated WebSocket rejection guard"
```

---

## Self-review checklist

- [x] Caddy: specific `/api/ingest/ws` handler declared before generic `/api/*` → WS upgrade headers are sent
- [x] Vite: `ws: true` added → dev-mode WebSocket proxy works
- [x] FastAPI: `get_backlinks` declared before `get_page` → `/{slug:path}/backlinks` is matched first
- [x] New tests cover the exact regression scenarios (route shadowing, nested slug, unauthenticated WS)
- [x] No placeholder steps — all code blocks are complete and runnable
- [x] No logic changes in existing functions — only declaration order and config
