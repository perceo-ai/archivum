.PHONY: up down build logs shell-backend shell-frontend setup uninstall rebuild-indexes lint-wiki dev

# ─── Docker ───────────────────────────────────────────────────────────────────

up:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — fill in your values before continuing" && exit 1; fi
	docker compose up

down:
	docker compose down

build:
	docker compose build

setup:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — fill in your values before continuing"; fi
	@./install.sh

uninstall:
	@./uninstall.sh

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

# ─── Dev shortcuts ────────────────────────────────────────────────────────────

dev-backend:
	cd backend && uv run uvicorn archivum.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# ─── Maintenance ──────────────────────────────────────────────────────────────

rebuild-indexes:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — fill in your values before continuing" && exit 1; fi
	curl -s -X POST http://localhost:8000/api/rebuild-indexes \
		-H "Authorization: Bearer $$(grep MCP_API_KEY .env | cut -d= -f2)" | jq .

lint-wiki:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — fill in your values before continuing" && exit 1; fi
	curl -s http://localhost:8000/api/lint \
		-H "Authorization: Bearer $$(grep MCP_API_KEY .env | cut -d= -f2)" | jq .

# ─── Shells ───────────────────────────────────────────────────────────────────

shell-backend:
	docker compose exec backend bash

shell-frontend:
	docker compose exec frontend sh

# ─── MCP client config ────────────────────────────────────────────────────────

print-mcp-config:
	@echo "─── Claude Code / Claude Desktop (~/.config/claude/mcp_servers.json) ───"
	@echo '{'
	@echo '  "archivum": {'
	@echo '    "command": "docker",'
	@echo '    "args": ["exec", "-i", "archivum-mcp", "python", "-m", "archivum.mcp.server", "--stdio"],'
	@echo '    "env": {"MCP_API_KEY": "'$$(grep MCP_API_KEY .env | cut -d= -f2)'"}'
	@echo '  }'
	@echo '}'
	@echo ""
	@echo "─── Cursor / Windsurf / VS Code (settings.json) ───"
	@echo '{'
	@echo '  "mcpServers": {'
	@echo '    "archivum": {'
	@echo '      "url": "http://localhost:8001/sse",'
	@echo '      "headers": {"Authorization": "Bearer '$$(grep MCP_API_KEY .env | cut -d= -f2)'"}'
	@echo '    }'
	@echo '  }'
	@echo '}'
