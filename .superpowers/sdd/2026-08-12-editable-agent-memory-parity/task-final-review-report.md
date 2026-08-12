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
  - `8 passed in 0.97s`.
- Relevant backend slice:
  - `cd apps/backend && uv run --group dev pytest ../../tests/api/test_context_api.py ../../tests/api/test_query.py ../../tests/retrieval/test_context_package.py ../../tests/retrieval/test_hybrid.py -q`
  - `24 passed in 1.01s`.
- Full backend suite:
  - `cd apps/backend && uv run --group dev pytest ../../tests -q`
  - `476 passed`, `3 failed`.
  - Failures are in unrelated untracked `../../tests/mcp_tests/test_sse_auth.py`, which expects `archivum.mcp.server.create_mcp`.
- Whitespace:
  - `git diff --check -- apps/backend/archivum/api/context.py tests/api/test_context_api.py`
  - Passed with no output.

## Commit

- Fix commit: `ddc5e83c92ac7ee4dfd047c306711a9d1d5c59f8` (`fix(api): constrain context package scopes`)

## Residual Risk

- REST context package access is now wiki-bound and repo-denying.
- Repository-scoped context remains available below the REST API for internal archgraph/retrieval callers. Future REST repo context support needs an explicit user-to-repository authorization model before allowing `repo:*`.
- The full backend suite is not green in this worktree because of the unrelated untracked MCP SSE auth test described above.
