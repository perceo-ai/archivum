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

---

# Final Review Report: REST Context Scope Authorization

## Summary

- Fixed `/api/context-package` so REST callers cannot choose arbitrary canonical knowledge scopes.
- The endpoint now derives the allowed scope from `CurrentUser.wiki_id` as `wiki:{wiki_id}`.
- Omitted scope and explicit current-wiki scope both resolve to the authenticated wiki scope.
- Explicit `wiki:<other>` scope overrides are rejected with HTTP 403 before database access.
- Repository scopes such as `repo:test` are also rejected with HTTP 403 at the REST boundary. I did not find an existing authorization model that grants authenticated wiki users access to repository scopes; internal lower-level retrieval code still supports repo scopes for non-REST callers.

## Tests

- Red verification before the fix:
  - `cd apps/backend && uv run --group dev pytest ../../tests/api/test_context_api.py -q`
  - Failed as expected because forbidden `wiki:other` and `repo:test` scopes did not raise `HTTPException`.
- Focused verification after the fix:
  - `cd apps/backend && uv run --group dev pytest ../../tests/api/test_context_api.py -q`
  - `8 passed in 1.01s`.
- Relevant backend slice:
  - `cd apps/backend && uv run --group dev pytest ../../tests/api/test_context_api.py ../../tests/api/test_query.py ../../tests/retrieval/test_context_package.py ../../tests/retrieval/test_hybrid.py -q`
  - `24 passed in 1.05s`.
- Full backend suite:
  - `cd apps/backend && uv run --group dev pytest ../../tests -q`
  - First run before the MCP SSE auth changes in this worktree: `476 passed`, `3 failed` in unrelated untracked `../../tests/mcp_tests/test_sse_auth.py`, which expected `archivum.mcp.server.create_mcp`.
  - Post-commit rerun after the concurrent MCP SSE auth changes: hung in `../../tests/mcp_tests/test_sse_auth.py::test_sse_transport_allows_valid_configured_bearer_token_to_list_tools`; interrupted after `348 passed in 132.91s`.
- Whitespace:
  - `git diff --check -- apps/backend/archivum/api/context.py tests/api/test_context_api.py`
  - Passed with no output.

## Commit

- Fix commit: `ddc5e83c92ac7ee4dfd047c306711a9d1d5c59f8` (`fix(api): constrain context package scopes`)
- Report commit before concurrent report edits: `e0af2d975a1d0eaec3a3828003ee13763cb39bc4` (`docs: record final review scope fix`)

## Residual Risk

- REST context package access is now wiki-bound and repo-denying.
- Repository-scoped context remains available below the REST API for internal archgraph/retrieval callers. Future REST repo context support needs an explicit user-to-repository authorization model before allowing `repo:*`.
- The full backend suite did not complete cleanly in this worktree because of the concurrent MCP SSE auth test state described above.

---

# Final Review Report: Owner Root and Projection Isolation

## Summary

- Fixed the global `person:self` owner node so it keeps a stable global scope instead of being overwritten by whichever wiki was edited last.
- Owner relationships now inherit the target object's scope, preserving wiki-specific `authored_thought` and `owns_project` edges from the global self node.
- Scoped context package construction injects the global self node into wiki-scoped contexts without broadening relationship scope.
- Canonical projection rebuild now projects only records for the requested `wiki:{wiki_id}` plus the global self node, and drops relationships whose endpoints are outside that filtered object set.
- Added regression coverage for root stability across wikis and projection isolation from other wiki/repo scopes.

## Tests

- `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_personal_root.py ../../tests/knowledge/test_markdown_projection.py ../../tests/knowledge/test_projections.py ../../tests/retrieval/test_context_package.py -q`
  - `24 passed`.
- Combined final-review critical fix slice:
  - `cd apps/backend && uv run --group dev pytest ../../tests/api/test_context_api.py ../../tests/mcp_tests/test_sse_auth.py ../../tests/mcp_tests ../../tests/knowledge/test_personal_root.py ../../tests/knowledge/test_markdown_projection.py ../../tests/knowledge/test_projections.py ../../tests/retrieval/test_context_package.py ../../tests/retrieval/test_hybrid.py ../../tests/api/test_query.py ../../tests/test_pages_backlinks.py -q`
  - `62 passed`, with two upstream `websockets`/`uvicorn` deprecation warnings.
- Full backend suite after all Critical fixes:
  - `cd apps/backend && uv run --group dev pytest ../../tests -q`
  - `479 passed`, with the same two upstream `websockets`/`uvicorn` deprecation warnings.

## Commit

- Fix commit: `79f1bbd` (`fix(knowledge): isolate owner root and projections by scope`)

## Residual Risk

- Projection isolation is covered with mocked Qdrant/Kuzu writes. A real two-wiki Kuzu/Qdrant integration smoke remains useful before release.
