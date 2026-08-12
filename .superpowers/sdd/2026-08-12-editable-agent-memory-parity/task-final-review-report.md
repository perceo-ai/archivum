# Final Review Report: MCP Bearer Authentication

## Summary

- Fixed MCP SSE bearer enforcement by wiring `MCP_API_KEY` into FastMCP's supported `TokenVerifier`/auth middleware path.
- Added a fail-closed tool guard so configured MCP tool calls require an authenticated FastMCP access-token context.
- Added regression coverage for unauthenticated SSE connect rejection, unauthenticated message/tool POST rejection, and successful authenticated SSE tool access with the configured bearer token.
- Changed MCP's process host default to `127.0.0.1` for non-container runs.
- Changed Docker Compose MCP publishing from all host interfaces to `127.0.0.1:${ARCHIVUM_MCP_PORT:-8001}:8001`; the container still sets `MCP_HOST=0.0.0.0` so the localhost host bind can reach it.
- Documented `ARCHIVUM_MCP_PORT` in `.env.example`.

## Tests

- Red verification before the fix:
  - `cd apps/backend && uv run pytest ../../tests/mcp_tests/test_sse_auth.py -q`
  - Failed as expected because `archivum.mcp.server.create_mcp` did not exist and MCP had no configured auth construction path.
- Focused verification after the fix:
  - `cd apps/backend && uv run pytest ../../tests/mcp_tests/test_sse_auth.py -q`
  - `3 passed`, with two upstream `websockets`/`uvicorn` deprecation warnings.
- MCP regression suite:
  - `cd apps/backend && uv run pytest ../../tests/mcp_tests -q`
  - `16 passed`, with the same two upstream deprecation warnings.
- Full backend suite:
  - `cd apps/backend && uv run --group dev pytest ../../tests -q`
  - `479 passed`, with the same two upstream deprecation warnings.
- Whitespace:
  - `git diff --check -- .env.example apps/backend/archivum/config.py apps/backend/archivum/mcp/server.py docker-compose.yml tests/mcp_tests/test_sse_auth.py`
  - Passed with no output.
- Compose render:
  - `docker compose config`
  - Confirmed the MCP published port renders with `host_ip: 127.0.0.1`.

## Commit

- Fix commit: `d5d1f54eeff4de951540987a35a08ef8cd9b7420` (`fix(mcp): enforce bearer auth for SSE`)

## Residual Risk

- This uses FastMCP's bearer-token middleware with a static configured token, not a full OAuth authorization server or scoped token rotation model.
- MCP stdio has no HTTP Authorization header. With `MCP_API_KEY` configured, the tool-level guard fails closed for direct stdio tool calls because no authenticated transport context exists; SSE is the supported authenticated transport.
