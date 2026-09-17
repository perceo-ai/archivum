# Agent Self-Setup and Cross-Machine Memory

_2026-09-17_

## Problem

Archivum is linked on this laptop and authenticates, yet the vault holds only
hand-written pages. Nothing an agent does reaches it. Four causes, each
independent:

1. The installed `archivum-memory` skill gates on "a repository Archivum has
   indexed". Zero repositories are indexed, so the precondition is permanently
   false and the skill never fires — which is what keeps repositories unindexed.
2. `AGENTS.md` and `CLAUDE.md` never mention Archivum. The product's own repo
   does not tell agents to use the product.
3. `register_repo` raises `"not a directory on this server"` (`code_repos.py:159`).
   Indexing resolves paths on the server, which cannot see any client's disk.
4. Session capture reads a bind mount. The mount is on the server VM; the
   transcripts are on the laptop. A mount does not cross machines.

Setup also requires a by-hand `git clone` because `@pranavkannepalli/archivum` is
unpublished, and only three clients (`claude`, `cursor`, `codex`) have config
writers.

## Goals

Any agent, on any machine, provisions itself against the user's server with no
manual clone and no copy-paste. Code indexing and session capture work from
machines the server cannot read. Browser clients (claude.ai, ChatGPT) are
first-class.

## Non-goals

Publishing to a public registry. Multi-user or team provisioning. Replacing
`CLAUDE.md` for instructions that must load unconditionally.

## A. Zero-install provisioning

### Distribution

The server serves its own installer, so the URL carries the server identity and
the CLI version can never drift from the server it talks to.

```
curl -fsSL https://<server>/install | sh      # GET /install
iwr https://<server>/install.ps1 | iex        # GET /install.ps1
```

The script downloads the CLI (pure JS, zero dependencies) from
`GET /install/cli.tar.gz`, unpacks to `~/.archivum/cli`, links
`~/.local/bin/archivum`, then runs `archivum connect --auto`.

### Provisioning token

A key class distinct from device keys, not a longer-lived one.

- Prefix `arch1p_`, stored hashed in a new `provisioning_tokens` table.
- Valid for exactly one endpoint: `POST /api/mcp/pairing/provision`. It cannot
  call any MCP tool; `_require_key` rejects it by prefix. A leak mints devices
  and reads nothing.
- Guards: per-token device cap, rate limit, optional TTL, and an activity entry
  per mint so minting appears in the stream rather than silently.
- Re-provisioning a known machine fingerprint revokes that machine's prior key,
  matching what `connect` already does on re-run.
- Read from `ARCHIVUM_PROVISION_TOKEN`.

Absent that variable, the CLI falls back to `POST /api/mcp/pairing/request`,
which creates a pending row the owner approves once in Settings while the agent
polls. Zero-touch when configured, one tap when not, never a dead end.

### Client registry

`GET /api/mcp/clients` returns a versioned manifest. Each entry carries: `id`,
display name, detection markers, config path, format
(`json-merge` | `toml-merge` | `yaml-merge` | `command`), the key path to merge
at, transport preference, whether the client interpolates environment variables,
and its transcript directory (reused by subsystem C).

`CLIENT_WRITERS` stops being a hardcoded map of three and becomes a generic
executor of manifest entries. Supporting a new client is a server-side data edit
that every machine picks up on its next run — no release, no reinstall.

Seeded entries:

| Client | Config | Shape |
|---|---|---|
| Claude Code | `claude mcp add --scope user` | command (existing special case) |
| Cursor | `~/.cursor/mcp.json` | `mcpServers.<name>` , `/sse` |
| Codex | `~/.codex/config.toml` | toml, `/mcp` streamable |
| Hermes Agent | `~/.hermes/config.yaml` | `mcp_servers.<name>`, `url` + `headers`; key written to `~/.hermes/.env`, referenced as `${env:ARCHIVUM_KEY}` |
| OpenClaw | path to confirm | `url` + `headers`; `transport: streamable-http` |

Sources disagree on OpenClaw's config location (`~/.openclaw/openclaw.json` with
a top-level `mcpServers` key, versus `.openclaw/config.json` with nested
`mcp.servers`). Confirm against an installed copy before seeding; the manifest
makes correcting it a data change.

Undetected clients get an exact printed snippet rather than silence.

### Browser clients

claude.ai and ChatGPT cannot run an installer. Settings gains a **Connect a web
client** panel: the public `/mcp` URL, a freshly minted named device key, and
copy buttons, with the key shown once. These require the server to be reachable
over public HTTPS, which is called out in the panel rather than discovered
through a failed connector.

### Skill fix

The skill's trigger is rewritten to fire on unindexed repositories too, offering
indexing as its first action, which breaks the deadlock in cause 1. `AGENTS.md`
gains a short section pointing agents at it, fixing cause 2.

## B. Cross-machine code indexing

The client walks, the server embeds.

As built, the client sends files rather than chunks. Chunking on the client
would have meant a second implementation of a pipeline that is already written
and tested: `ingest_repo` takes a directory, and `snapshot_repo` degrades to
`working-tree` when there is no git history, so a staged tree is enough. Moving
bytes instead of reimplementing the parser keeps one code path.

- `archivum index` selects files with `git ls-files -co --exclude-standard`,
  which is `.gitignore` honoured exactly rather than approximated. Non-git
  directories fall back to a walk with a skip list.
- Binaries (detected by a NUL byte, as git does), files over 2MB, and obvious
  non-source extensions are dropped; symlinks are never followed.
- `POST /api/repos/upload` is device-authenticated, unpacks into a staging
  directory under the code cache, and runs the existing `index_repo` unchanged.
- Extraction refuses rather than sanitises: absolute paths, `..` traversal,
  symlinks, hard links, device nodes, oversize expansion, too many members. A
  refused archive leaves nothing behind.
- Re-uploading replaces the staged tree rather than merging, so a file deleted
  since the last upload does not survive in the index.

Incremental indexing by `since_sha` does not apply to an uploaded tree, so each
upload is a full reindex. That is the cost of not shipping git history.

## C. Cross-machine session capture

The existing watcher, relocated to where the transcripts are.

As built, the client ships redacted transcript files and the server parses them
with the importers it already has — same reasoning as B: one parser, not one per
client language.

- `archivum watch` sweeps the transcript directories named by the client
  registry and recorded into the link state at connect time, so config paths and
  transcript paths cannot drift apart.
- Redaction runs before anything leaves the machine: provider keys, GitHub and
  Slack tokens, Google keys, AWS ids, PEM private-key blocks, Archivum's own
  `amk_`/`arch1_`/`arch1p_` keys, and `KEY=value` assignments.
- `POST /api/sources/capture/upload` is device-authenticated and reuses `connector_for`
  and `CaptureStore`. Capture is content-addressed, so re-sending an unchanged
  transcript deduplicates rather than duplicating — which is what lets the
  watcher re-send whenever it is unsure.
- Change detection is size plus mtime, not a hash of every file each pass; a
  failed upload is recorded so one unparseable transcript is not retried forever.

Transcript upload is the largest privacy surface in this design: it ships
everything ever typed in a session. Redaction is a set of shapes, not a
guarantee — a secret that looks like prose survives. Nothing starts the watcher
automatically for that reason; it is opt-in per machine.

## Verification

```bash
npm test --workspace apps/frontend
npm run build --workspace apps/frontend
npm test --workspace packages/archivum-cli
cd apps/backend && uv run --group dev pytest ../../tests -q
```

End to end: provision a machine with only the install line and
`ARCHIVUM_PROVISION_TOKEN` set; confirm a key is minted, configs are written for
every detected client, `list_repositories` returns the indexed repo after a
client-side index, and `recall_fix` returns a recorded fix.
