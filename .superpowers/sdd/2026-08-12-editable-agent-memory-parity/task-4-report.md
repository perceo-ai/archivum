# Task 4 Report: Canonical Code Knowledge Persistence

## Status

DONE

## Implementation

- Added adapters from extracted code candidates to `KnowledgeObject` and
  `KnowledgeRelationship`, preserving provenance citations, confidence,
  extraction method, and source scope.
- Updated `ingest_repo` to write accepted code objects and relationships to a
  supplied `KnowledgeRepository`. The fake validation argument remains only as
  a compatibility path for existing unconverted tests.
- Updated the command runner to initialize and use the canonical knowledge
  schema in its SQLite database. Lexical indexing remains a rebuildable
  projection in the same database.
- Kept graph export working by adapting canonical records at the hook boundary.

## Verification

- RED: `cd apps/backend && uv run --group dev pytest ../../tests/archgraph/test_ingest.py::test_archgraph_ingest_writes_to_knowledge_repository -q`
  failed as expected before implementation: `ingest_repo() got an unexpected keyword argument 'knowledge'`.
- GREEN: the same command passed after implementation: `1 passed`.
- Required suite: `cd apps/backend && uv run --group dev pytest ../../tests/archgraph -q`
  passed: `62 passed in 2.40s`.
- `git diff --check` completed with no whitespace errors.

## Scope

Only Task 4 backend archgraph files, the repository-backed ingest regression
test, and this report are included in the commit.

## Review Fix: Canonical Persistence Hardening

### Changes

- `ingest_repo` now requires `KnowledgeRepository`; the validation sink argument
  and all ingest/end-to-end test uses were removed. The remaining fake
  validation fixture exercises only the standalone mapper validation test and
  is not reachable from ingestion.
- The CLI now stores canonical records in `<repo>/.archivum/knowledge.db` and
  retains `<cache_dir>/index.db` solely for the rebuildable lexical index.
- Added repository cleanup for objects and relationships whose complete
  provenance citation set belongs to files deleted in an incremental update.
- Strengthened canonical ingest assertions for relationships, citations,
  extraction methods, and source scope. Added persisted object and cross-file
  relationship cleanup coverage plus a hook test proving lexical cache storage
  does not contain canonical tables.

### Reviewer Self-Check

The ingest mapping output remains complete: `repo_artifacts` supplies repos and
commits, while `map_extraction` maps symbols, files, and extracted relations
such as calls, imports, and references through the canonical adapters.

### Verification

- Focused cleanup and retrieval coverage passed:
  `cd apps/backend && uv run --group dev pytest ../../tests/archgraph/test_ingest.py::test_archgraph_ingest_writes_to_knowledge_repository ../../tests/archgraph/test_ingest.py::test_update_prunes_deleted_file ../../tests/archgraph/test_end_to_end.py -q`
  (`5 passed`).
- Required suite passed:
  `cd apps/backend && uv run --group dev pytest ../../tests/archgraph -q`
  (`62 passed in 2.70s`).
