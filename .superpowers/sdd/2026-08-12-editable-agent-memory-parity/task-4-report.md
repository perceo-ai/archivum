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
