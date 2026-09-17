# Archivum Claude Instructions

Follow [AGENTS.md](AGENTS.md). Claude-specific agents should use the same product direction, docs source of truth, Linear workflow, and verification rules.

## Archivum memory

This machine is linked to Archivum, and this repository is the product. Use it:

- **Before debugging anything**, call `recall_fix(symptom="<the error>")`. An
  empty answer says so; that is also information.
- **Before changing unfamiliar code**, call
  `retrieve_code_context(query=..., repo="archivum")`.
- **When something mattered** — a non-obvious cause, a decision with a reason, a
  gotcha worth warning the next person about — call `record_work(...)` and say
  what the *cause* was, not just the symptom.
- If `list_repositories` does not list this repo, run `archivum index` in a
  shell here first. `index_repository` resolves paths on the server and will
  fail from this machine.

The `archivum-memory` skill has the full version. If Archivum is unreachable,
say so and carry on — memory is an advantage, not a dependency.
