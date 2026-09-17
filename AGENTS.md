# Archivum Agent Instructions

## Project Context

Archivum work lives in the Linear `Archivum` project.

When pulling work from Linear in this repository:

- Query the `Archivum` project specifically.
- Be specific with Linear queries: project, status, assignee, issue key, labels, and relevant text.
- When starting a Linear task, move it to `In Progress`.
- When finishing a Linear task, move it to `In Review` so the user can review and push.

## Product Direction

**Archivum is where the non-code artifacts your agents need live, reachable from
every machine you work on.**

Three jobs, in priority order:

1. **Product and project definitions.** What a thing is, why it is built that
   way, what was decided. These outlive any repository and are needed from
   machines that do not have that repository checked out.
2. **Repetitive procedures.** The things you would otherwise re-explain every
   session. Skills belong here, synced to every linked machine.
3. **Code graphs.** A repository read into symbols and relationships an agent
   can query — the graphify idea applied to code.

The common thread is *off git, on every device*. Git is per-repository and
needs a checkout; these artifacts span repositories and must be reachable from
a laptop that has none of them.

### Two constraints on how this is written

- Never claim Archivum recalls faster than markdown files on disk. Reading a
  local `CLAUDE.md` is a filesystem read; Archivum retrieval is a network round
  trip plus ranking, so it is slower per call. The honest and stronger claim is
  less context for the same answer, and the same memory on every machine.
- Do not describe Archivum as Archductor or Archfleet work unless it is clearly
  a private integration note.

### History, so the next agent does not re-litigate it

This product has been defined three times and the code still carries all three.
Read this before proposing anything that sounds like a return to one of them.

| Date | It was defined as | What that left behind |
|---|---|---|
| 2026-07-28 | A memory layer for a person's whole work and life, explicitly *not* a wiki | `life_os`, entities, timeline |
| 2026-08-12 | "It keeps my knowledge clean" — abundant capture, scarce promotion | memory assets, distillation, the review queue |
| 2026-09 | Self-hosted memory for coding agents across machines | code graph, per-device keys, `archivum index` |

Nothing was ever removed, which is why there are 123 REST routes and 29 MCP
tools for a product that needs a fraction of them.

### Outside the definition

These exist and work to varying degrees. They are **not** the product. Do not
extend them, do not feature them in docs, and prefer removing them to improving
them:

- Sharing, grants, public wiki, HTML/PDF export
- Session capture and transcript storage — `archivum watch` and the server-side
  transcript watcher. The owner does not want conversation transcripts stored.
- Life OS daily notes and project registration
- The suggestion review queue

An agent measurement on 2026-09-17 found that guidance alone does not make
agents record what they learn: four subagents did real work in this repository
and none of them wrote to the vault, with the tools and the skill both
available. Treat "an agent will remember to call it" as false until shown
otherwise.

## Use Archivum

This repository is the product. Agents working in it use it, and the fastest way
to find a gap is to hit it yourself.

- Before debugging: `recall_fix(symptom="<the error>")`. An empty answer says so.
- Before changing unfamiliar code: `retrieve_code_context(query=..., repo="archivum")`.
- If `list_repositories` does not list this repo, `index_repository` it first.
- When work mattered, `record_work(...)` with the cause, not just the symptom.

The `archivum-memory` skill covers this in full and is installed by
`archivum connect`. If Archivum is unreachable, say so and carry on — memory is
an advantage, not a dependency.

## Agent Source of Truth

Read these before making product/docs changes:

- `README.md` for customer-facing install/product docs.
- `docs/README.md` for the docs map.
- `docs/agent-guide.md` for coding-agent orientation.
- `docs/project/progress.md` for verified/partial/unknown status.
- `.env.example`, `docker-compose.yml`, and `docker-compose.images.yml` for runtime truth.

Old PRD, operator handoff, and root `Progress.md` docs were intentionally pruned. Do not recreate them unless the user explicitly asks.

## Verification

Run the relevant checks before claiming completion:

```bash
npm test --workspace apps/frontend
npm run build --workspace apps/frontend
npm test --workspace packages/archivum-cli
cd apps/backend && uv run --group dev pytest ../../tests -q
```

For docs-only changes, also scan for stale language:

```bash
rg -n "scripts/[b]ootstrap|[N]eo4j|[y]ou@youremail|[L]ast updated: 2026-06|[f]eature complete" -g "*.md" -g "!node_modules/**" -g "!apps/backend/.venv/**"
```
