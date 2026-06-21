.PHONY: up down build logs shell-backend shell-frontend setup uninstall rebuild-indexes lint-wiki dev graph-export-demo mcp-demo mcp-smoke

# ─── Docker ───────────────────────────────────────────────────────────────────

up:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — fill in your values before continuing" && exit 1; fi
	node packages/archivum-cli/src/index.js stack up

down:
	node packages/archivum-cli/src/index.js stack down

build:
	node packages/archivum-cli/src/index.js stack build

setup:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — fill in your values before continuing"; fi
	@node packages/archivum-cli/src/index.js install

uninstall:
	@node packages/archivum-cli/src/index.js uninstall

logs:
	node packages/archivum-cli/src/index.js stack logs

logs-backend:
	node packages/archivum-cli/src/index.js stack logs backend

# ─── Dev shortcuts ────────────────────────────────────────────────────────────

dev-backend:
	cd apps/backend && uv run uvicorn archivum.main:app --reload --port 8000

dev-frontend:
	cd apps/frontend && npm run dev

# ─── Maintenance ──────────────────────────────────────────────────────────────

rebuild-indexes:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — fill in your values before continuing" && exit 1; fi
	node packages/archivum-cli/src/index.js wiki rebuild-indexes

lint-wiki:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — fill in your values before continuing" && exit 1; fi
	node packages/archivum-cli/src/index.js wiki lint

graph-export-demo:
	cd backend && python3 -m archivum.scripts.graph_export --demo --output-dir ../graph-export-out
	@echo "OK: graph-export-out/graph.json and graph-export-out/graph.html written"

# ─── Shells ───────────────────────────────────────────────────────────────────

shell-backend:
	node packages/archivum-cli/src/index.js stack shell backend

shell-frontend:
	node packages/archivum-cli/src/index.js stack shell frontend

# ─── MCP client config ────────────────────────────────────────────────────────

print-mcp-config:
	@node packages/archivum-cli/src/index.js mcp config --client claude

# ─── MCP Demo ─────────────────────────────────────────────────────────────────

mcp-demo:
	cd apps/backend && uv run python -m archivum.mcp.demo
	@echo "OK: mcp-demo-out/ written"

mcp-smoke:
	cd apps/backend && uv run pytest ../../tests/mcp_tests/test_stdio_smoke.py -q
