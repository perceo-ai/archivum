# Archivum — Product Requirements Document

> **Name:** Archivum — Latin root of "archive." The actual source word, more distinctive than archive itself. Deploy at `archivum.madebypranav.dev` for v1; register `archivumapp.com` before public launch.

**Status:** Draft  
**Author:** TBD  
**Date:** April 2026  
**Version:** 1.0  
**Timeline:** 1 week build  
**Stakeholders:** Builder (solo), future product users

---

## 1. Executive Summary

Archivum is a self-hosted, AI-powered knowledge base that runs entirely on a home server via Docker. Unlike existing tools (Notion, Obsidian, NotebookLM), it does not treat every query as a clean slate. Instead, an AI agent incrementally builds and maintains a persistent wiki — writing markdown pages, embedding them for semantic search, and syncing relationships into a graph database — so that knowledge compounds with every source added and every question asked.

The v1 target is a single-user deployment: one `docker compose up` command brings up a full stack including a web UI with a built-in markdown editor (CodeMirror 6, replacing Obsidian), a REST API, and an MCP server compatible with every major MCP client — Claude Desktop, Claude Code, Cursor, Windsurf, VS Code, Zed, ChatGPT, Gemini, and Copilot. There are no subscriptions, no closed-source dependencies, and no data leaving the home network (except the LLM API call itself, which can also be made local via Ollama).

The system is architected from day one to be multi-tenant and packageable — so that after the personal v1 is validated, it can be turned into a distributable product without a rewrite.

---

## 2. Name & Brand

### Name: Archivum

**Domain:** `archivum.madebypranav.dev` (v1) → `archivumapp.com` (public launch)  
**GitHub:** `github.com/archivum`  
**Docker image:** `archivumapp/archivum`

**Why Archivum:**
- Latin root of "archive" — the actual source word, immediately understood globally
- No dominant product owns this name in the PKM or developer tools space
- Works as a GitHub org (`archivum`), Docker image (`archivumapp/archivum`), and domain (`archivumapp.com`)
- Scales from personal tool to product brand — Archivum sounds like infrastructure, which is exactly what it is

**Other names considered:**

| Name | Notes |
|---|---|
| Folio | Clean one-word name, considered but moved on |
| Lore | Clean and evocative, but conflicts with gaming/D&D tooling |
| Vaultmind | Compound, too long |
| Papertrail | Taken (log management SaaS) |
| Commonplace | Accurate (commonplace book = historical knowledge base) but too generic |
| Nexus | Overused across every category |
| Palimpsest | Brilliant word, impossible to spell |
| Vaulted | Taken by two unrelated apps |
| Grotto | Evocative but obscure |

**Tagline options:**
- *"Your knowledge base, compiled."* — technical, precise
- *"The wiki that writes itself."* — punchy, explains the core idea
- *"Knowledge that compounds."* — investor/product-speak, future-facing

---

## 3. Problem Statement

### Current State

Personal knowledge management tools fall into two camps:

1. **Manual wikis** (Obsidian, Notion, Confluence) — require the user to do all the bookkeeping: writing summaries, maintaining cross-references, updating links. In practice, nobody does this consistently. Wikis rot. Obsidian specifically requires a paid subscription for sync across devices and is closed-source.

2. **LLM retrieval tools** (NotebookLM, ChatGPT file upload, RAG systems) — treat every query as a clean slate. The model retrieves chunks, generates an answer, discards the synthesis. Nothing accumulates.

Neither gives you a knowledge base that gets *better* over time without constant manual effort.

### Pain Points

- Losing track of research across articles, papers, notes, and conversations
- Paying for Obsidian Sync just to access notes from multiple devices
- Obsidian being closed-source with no self-hostable sync
- Spending time on bookkeeping that an LLM could do
- RAG tools that re-derive knowledge from scratch on every query
- No programmatic access to the knowledge base for AI agents

### Why Now

LLMs are now good enough to do the maintenance work reliably. The tooling to run them locally has matured. Docker makes self-hosted multi-service stacks trivial. MCP has become the universal standard — supported by every major AI client — meaning one MCP server exposes Archivum to the entire agent ecosystem at once.

---

## 4. Goals & Objectives

### Business Goals

- Validate the core loop: ingest → wiki grows → query returns better answers over time
- Prove the stack is stable enough for daily use within one week
- Establish an architecture that supports a future multi-user product without a rewrite

### Business Goals (product launch)

- Distribute as a Docker image, hosted SaaS, or packaged app
- Replace Obsidian + RAG tool for knowledge workers
- Charge for hosted version or premium features (multi-user, cloud backup, mobile)
- Submit to MCP registries (Glama, mcp.so) to drive organic discovery

### User Goals

- Replace Obsidian entirely — free, open, self-hosted
- Wiki with 100+ agent-authored pages after 3 months
- Query the wiki in natural language daily
- Let Claude Code and other agents drive the wiki via MCP
- Stop losing track of research

### Non-Goals

- Fine-tuning or training on wiki content
- Real-time collaborative multi-cursor editing (last-write-wins is sufficient)
- Automatic source crawling or RSS ingestion without user action
- Native iOS/Android app (responsive web UI on Tailscale covers mobile)
- Obsidian plugin compatibility



---

## 5. User Personas

### Primary Persona: The Solo Builder / Knowledge Worker

- **Role:** Developer, researcher, or power user running their own home server
- **Context:** Has accumulated research, articles, notes across many tools. Currently uses Obsidian but resents the sync paywall and closed-source nature. Uses Claude Code or Cursor regularly.
- **Needs:** A knowledge base that maintains itself, is accessible from any device on the home network, and can be driven by AI agents as well as directly via a browser.
- **Pain Points:** Manual bookkeeping overhead, Obsidian Sync cost, no programmatic API for their knowledge base, losing research to chat history.

### Secondary Persona: The Small Team

- **Role:** 2–5 person team (startup, research group, household)
- **Context:** Wants a shared knowledge base fed by Slack threads, meeting notes, documents. No one wants to maintain it manually.
- **Needs:** Multi-user access, role-based permissions, team ingest workflows, invite-based access.

---

## 6. User Stories & Requirements

### Epic 1: Ingest

Archivum accepts a wide range of file types. The pipeline is the same regardless of format: file lands in `/raw` → parser extracts clean text and metadata → LLM processes into wiki pages → Qdrant + Neo4j updated.

#### Supported file types

All parsers feed the same pipeline: extracted text → LLM → markdown pages → Qdrant → Neo4j.

| Category | Formats | Parser |
|---|---|---|
| Markdown / text | `.md`, `.txt`, `.rst` | Native — frontmatter parsing included |
| Documents | `.pdf` | PyMuPDF — text + basic metadata |
| Web / HTML | `.html`, `.htm` | BeautifulSoup — strips chrome, extracts body |
| URLs | `http://`, `https://` | httpx fetch → BeautifulSoup → HTML pipeline |
| Office | `.docx`, `.pptx`, `.xlsx` | `python-docx`, `python-pptx`, `openpyxl` |
| Data | `.csv`, `.json`, `.jsonl` | Pandas — summarises schema + sample rows |
| ePub | `.epub` | `ebooklib` — chapters as separate pages |
| Code | `.py`, `.js`, `.ts`, `.go`, `.rs`, `.sh` | AST-aware — extracts functions, classes, docstrings |
| Subtitles / transcripts | `.srt`, `.vtt` | Native — strips timestamps |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp` | Claude vision — caption + OCR |
| Audio | `.mp3`, `.m4a`, `.wav` | Whisper (local) — transcription |
| Video | `.mp4`, `.mov` | ffmpeg audio strip → Whisper |
| Email | `.eml`, `.mbox` | `mailparser` — body + metadata |

Unsupported file types are rejected at upload with a clear error listing accepted formats.

Files not in this list are rejected at upload with a clear error message listing supported types.

#### Story 1.1: Upload a source file
```
As a knowledge worker,
I want to drag and drop any supported file into the web UI,
So that the AI agent automatically processes it into my wiki regardless of format.

Acceptance Criteria:
- [ ] User can drag one or more files onto the ingest panel
- [ ] Unsupported file types rejected immediately with a clear error
- [ ] Correct parser selected automatically based on file extension + MIME type
- [ ] Ingest pipeline runs automatically on upload
- [ ] Progress streamed live to the UI per file
- [ ] On completion, summary of pages created/updated shown with links
- [ ] File written to /raw and never modified
- [ ] Failed ingests show the failure reason inline; do not leave partial wiki pages
```
**Priority:** P0 | **Estimate:** L

#### Story 1.2: Ingest a URL
```
As a knowledge worker,
I want to paste a URL into the ingest panel,
So that web articles and pages are pulled in without manual downloading.

Acceptance Criteria:
- [ ] URL input field available in the ingest panel alongside file drop
- [ ] Playwright fetches the page, readability extracts main content
- [ ] Extracted content runs through the standard HTML pipeline
- [ ] Original URL stored as source metadata on the resulting wiki page
- [ ] Paywalled or JS-heavy pages that fail to extract show a clear error
```
**Priority:** P0 | **Estimate:** M

#### Story 1.3: View ingest results
```
As a knowledge worker,
I want to see which wiki pages were created or updated after an ingest,
So that I can review what the agent did and correct anything wrong.

Acceptance Criteria:
- [ ] Ingest panel shows list of pages created and updated with clickable links
- [ ] Log entry appended to log.md automatically
- [ ] Ingest history accessible from Settings — full log of every source ever ingested
```
**Priority:** P0 | **Estimate:** S

#### Story 1.4: Batch ingest
```
As a knowledge worker,
I want to upload multiple files at once,
So that I can bulk-import an existing notes folder or research collection.

Acceptance Criteria:
- [ ] Up to 20 files uploadable in a single drag-drop
- [ ] Files processed sequentially (not in parallel) to avoid LLM rate limits
- [ ] Progress bar shows overall batch progress and per-file status
- [ ] Partial batch failure does not block remaining files
```
**Priority:** P0 | **Estimate:** M


---

### Epic 2: Editor

#### Story 2.1: Edit a wiki page
```
As a knowledge worker,
I want to edit wiki pages in a markdown editor in the browser,
So that I don't need Obsidian or any local app installed.

Acceptance Criteria:
- [ ] CodeMirror 6 editor renders with markdown syntax highlighting
- [ ] Changes auto-save within 1 second of last keystroke via WebSocket
- [ ] Save confirmed with a subtle status indicator
- [ ] Editor works on any device on the local network
```
**Priority:** P0 | **Estimate:** M

#### Story 2.2: Use wikilinks
```
As a knowledge worker,
I want to type [[Page name]] and have it autocomplete to existing pages,
So that I can link pages together the same way Obsidian works.

Acceptance Criteria:
- [ ] Typing [[ opens an autocomplete dropdown of existing page titles
- [ ] Selecting a suggestion completes the wikilink syntax
- [ ] Links to existing pages are visually distinct
- [ ] Links to non-existent pages shown in a different colour with "create page" tooltip
- [ ] Clicking a wikilink navigates to that page
```
**Priority:** P0 | **Estimate:** M

#### Story 2.3: See backlinks
```
As a knowledge worker,
I want to see which pages link to the page I'm currently editing,
So that I can understand how a page fits into the broader wiki.

Acceptance Criteria:
- [ ] Backlinks panel shown in sidebar when a page is open
- [ ] Each backlink is a clickable link to the source page
- [ ] Backlinks update in real time when another page is saved
```
**Priority:** P1 | **Estimate:** S

---

### Epic 3: Graph View

#### Story 3.1: Browse the knowledge graph
```
As a knowledge worker,
I want to see a force-directed graph of all my wiki pages and entities,
So that I can visually navigate my knowledge base.

Acceptance Criteria:
- [ ] Graph renders all page and entity nodes from Neo4j
- [ ] Nodes colour-coded by type (page, person, concept, organisation)
- [ ] Edges show relationship type (references, related-to, contradicts, mentions)
- [ ] Clicking a node opens its wiki page
- [ ] Graph supports zoom, pan, and node search/highlight
- [ ] Graph updates within 5 seconds of a new ingest completing
```
**Priority:** P0 | **Estimate:** L

---

### Epic 4: Query

#### Story 4.1: Ask a question against the wiki
```
As a knowledge worker,
I want to type a natural language question and get a synthesised answer,
So that I can query accumulated knowledge without manually searching pages.

Acceptance Criteria:
- [ ] Query input available in the UI
- [ ] Response streams token-by-token
- [ ] Response includes citations linked to specific wiki pages
- [ ] Query latency from submission to first token under 3 seconds
```
**Priority:** P0 | **Estimate:** M

#### Story 4.2: Save a query answer as a wiki page
```
As a knowledge worker,
I want to save a good query answer back into the wiki as a new page,
So that useful syntheses accumulate rather than disappearing into chat history.

Acceptance Criteria:
- [ ] "Save as page" button appears after a query response
- [ ] Clicking it creates a new wiki page with the answer as content
- [ ] New page is indexed in Qdrant and Neo4j automatically
```
**Priority:** P1 | **Estimate:** S

---

### Epic 5: Search

#### Story 5.1: Semantic search
```
As a knowledge worker,
I want to search my wiki using natural language,
So that I can find relevant pages even when I don't remember the exact wording.

Acceptance Criteria:
- [ ] Search bar accessible from any view
- [ ] Results returned via Qdrant vector similarity within 1 second
- [ ] Results show title, highlighted excerpt, and relevance indicator
- [ ] Keyword fallback search runs if vector results are sparse
```
**Priority:** P0 | **Estimate:** M

---

### Epic 6: MCP Server

#### Story 6.1: Connect from any MCP-compatible client
```
As a developer or agent user,
I want to connect any MCP-compatible client to Archivum,
So that Claude Code, Cursor, Windsurf, VS Code, ChatGPT, and others can
all drive my wiki without per-client configuration.

Acceptance Criteria:
- [ ] SSE transport runs at localhost:8001/sse (for remote/web clients)
- [ ] stdio transport available for desktop clients (Claude Desktop, Cursor, Zed)
- [ ] All 8 MCP tools callable from any compliant client
- [ ] Tool schemas pass MCP Inspector validation
- [ ] Tested against: Claude Code, Claude Desktop, Cursor, Windsurf
```
**Priority:** P0 | **Estimate:** M

---

### Epic 7: Lint

#### Story 7.1: Health-check the wiki
```
As a knowledge worker,
I want to run a lint pass that surfaces health issues,
So that I can keep the knowledge base clean over time.

Acceptance Criteria:
- [ ] Lint report lists orphan pages, contradictions, broken wikilinks
- [ ] Each issue has a suggested fix with a one-click apply button
```
**Priority:** P1 | **Estimate:** M

---

## 7. Success Metrics

### North Star Metric

**Agent-authored wiki pages** — count of pages whose last write was by the agent, not the user.

- Baseline: 0 at launch
- Target: 100+ by end of week 3

### OKRs — Week 1

**Objective:** Ship a working self-hosted wiki stack in one week

- KR1: `docker compose up` boots all services with zero manual steps beyond `.env`
- KR2: Full ingest → query loop works end-to-end
- KR3: CodeMirror 6 editor with `[[wikilink]]` autocomplete functional
- KR4: MCP server passes MCP Inspector validation and connects from Claude Code
- KR5: Graph view renders from Neo4j

### Supporting Metrics (3-month personal use)

| Metric | Baseline | Target | Timeframe |
|---|---|---|---|
| Agent-authored wiki pages | 0 | 100+ | 3 months |
| Daily query sessions | 0 | 1+ per day | Month 2 |
| Sources ingested | 0 | 50+ | 3 months |
| MCP tool calls per week | 0 | 10+ | Month 2 |

---

## 8. Scope

### In Scope

- Docker Compose stack: Web UI, REST API, MCP Server, Wiki Agent, Qdrant, Neo4j
- CodeMirror 6 editor: markdown highlighting, `[[wikilink]]` autocomplete, live preview, auto-save
- File sidebar: create, rename, delete, drag-drop upload
- Graph view: force-directed, Neo4j-backed, click-to-open
- Ingest pipeline: all supported file types + URL ingest → parser → LLM extract → markdown → Qdrant → Neo4j
- Query: Qdrant semantic + Neo4j multi-hop + LLM synthesis + streaming
- MCP server: **both SSE and stdio transports**, 8 tools, MCP Inspector validated
- Single-user auth: shared API key
- `POST /api/rebuild-indexes`

### Out of Scope

- Multi-user auth / RBAC
- Cloud hosting
- Automatic RSS / web crawling

---

## 9. Technical Considerations

### MCP Server — Full Client Compatibility

MCP is now supported by every major AI client. To ensure Archivum works with all of them, the MCP server must implement **both transports**:

| Transport | Used by |
|---|---|
| **stdio** | Claude Desktop, Claude Code, Cursor, Windsurf, Zed, VS Code (local) |
| **HTTP/SSE** | ChatGPT plugins, Gemini extensions, web-based clients, remote agents |

**Implementation approach:** Use the official Python MCP SDK which supports both transports from a single server definition. The `docker-compose.yml` exposes SSE on port 8001. For stdio, users add Archivum to their client config pointing at the container via `docker exec` or a thin wrapper script.

**Client config snippets to ship in README:**

```jsonc
// Claude Desktop / Claude Code (~/.config/claude/mcp_servers.json)
{
  "folio": {
    "command": "docker",
    "args": ["exec", "-i", "folio-mcp", "python", "-m", "folio.mcp"],
    "transport": "stdio"
  }
}

// Cursor / Windsurf / VS Code (settings.json)
{
  "mcpServers": {
    "folio": {
      "url": "http://localhost:8001/sse"
    }
  }
}
```

**Validation:** Run `npx @modelcontextprotocol/inspector` against both transports before shipping. All 8 tools must pass schema validation.

### MCP Tools

| Tool | Description |
|---|---|
| `ingest_source` | Process a file path or URL into the wiki |
| `search_wiki` | Semantic search; returns top-k with excerpts |
| `get_page` | Retrieve full markdown content by slug |
| `list_pages` | List pages with optional tag/type filter |
| `write_page` | Create or update a page and re-index |
| `query` | Ask a question; returns synthesised answer with citations |
| `graph_neighbors` | Return Neo4j neighbors of an entity |
| `lint_wiki` | Run health check; returns structured issue list |

### Architecture

Single Docker Compose file, `wiki-net` bridge network.

| Service | Tech | Port (host) |
|---|---|---|
| Web UI | React + Vite | 3000 |
| REST API | FastAPI (Python 3.12) | 8000 |
| MCP Server | Python MCP SDK (stdio + SSE) | 8001 |
| Wiki Agent | Python (internal) | — |
| Qdrant | `qdrant/qdrant` | 6333 (optional) |
| Neo4j | `neo4j:5` | 7474 (optional) |

### Storage

- Markdown files are canonical. Qdrant and Neo4j are derived and fully rebuildable.
- All data on named Docker volumes — survives restarts and upgrades.
- `wiki_id` field on all data models from day 1 for future multi-tenancy.

### Performance Targets

- Ingest of a 2,000–5,000 word article: under 60 seconds
- Query first-token latency: under 3 seconds
- Semantic search: under 1 second
- Graph view initial render (up to 500 nodes): under 2 seconds
- Editor auto-save round trip: under 500ms

---


---

## 10. Security Architecture

### Remote Access Model

Archivum never exposes a public port directly. All remote access is layered:

| Layer | Purpose | Who |
|---|---|---|
| Tailscale network | Full authenticated access to the UI, API, and MCP server | Owner + invited guests |
| Cloudflare Tunnel | Public share links only — read-only, token-gated, single subdomain | Anyone with a share link |
| LAN direct | Full access on home network without Tailscale | Owner on local devices |

The home router is never touched. No port forwarding required.

**Tailscale guest access:** Owner invites trusted people to their Tailscale network via email. Tailscale personal plan supports up to 3 users free. Guests install Tailscale, accept the invite, and reach Archivum at its stable Tailscale IP. They still need a valid Archivum account to log in.

**Cloudflare Tunnel for public links:** A single Cloudflare Tunnel exposes one subdomain (e.g. `share.archivum.madebypranav.dev`) for public share link rendering only. This subdomain serves only the share link viewer — it cannot be used to browse the wiki or log in.

---

### Authentication

| Method | Used for | v1? |
|---|---|---|
| Password login (owner) | Owner account set via `.env` on first boot | Yes |
| Invite token | Owner generates signed link; guest sets username + password | Yes |
| Share token | Unguessable URL token for public page/query sharing | Yes |
| OAuth / SSO | Google or GitHub login for future multi-user product | Yes |

**Session tokens:** Short-lived JWTs (15 min expiry) + refresh tokens (7 day expiry). Stored in `httpOnly`, `SameSite=Strict` cookies — never in `localStorage`. Resistant to XSS token theft.

**Password requirements:** Minimum 12 characters enforced server-side. Passwords hashed with bcrypt (cost factor 12).

---

### Permission Levels

| Role | Read | Write / Edit | Ingest | Manage users | Settings |
|---|---|---|---|---|---|
| Owner | ✓ | ✓ | ✓ | ✓ | ✓ |
| Collaborator | ✓ | ✓ | ✗ | ✗ | ✗ |
| Viewer | ✓ | ✗ | ✗ | ✗ | ✗ |
| Share link | Specific page or query result only | ✗ | ✗ | ✗ | ✗ |

Maximum 10 guest accounts in v1 — sufficient for personal + trusted collaborators, not a scaling concern yet.

---

### Security Hardening (v1)

| Control | Implementation |
|---|---|
| HTTPS everywhere | Caddy reverse proxy with auto TLS. All traffic encrypted including on LAN. |
| CSRF protection | `SameSite=Strict` cookies + CSRF token on all mutating requests. |
| Rate limiting | Login: 10 attempts / 15 min / IP then lockout. Share views: 100 / hr. API: 60 req / min per token. |
| Content Security Policy | Strict CSP headers on all responses. Inline scripts blocked. Prevents XSS in rendered markdown. |
| Markdown sanitisation | **Critical.** All LLM-generated and user-submitted markdown sanitised before rendering. DOMPurify on client, `bleach` on server. No raw HTML passthrough. |
| Secrets management | All secrets in `.env` only — LLM API key, JWT secret, DB passwords, Tailscale auth key. `.env.example` ships with placeholders and no real values. |
| Read-only raw volume | `/raw` Docker volume mounted `read-only` to all services except the ingest pipeline. Sources cannot be overwritten by a bug or a compromised service. |
| Non-root containers | All Docker services run as non-root users. |
| No direct DB exposure | Qdrant and Neo4j ports not exposed to host by default. Accessible only within `archivum-net`. |

---

## 11. Sharing

### Share Features

| Feature | How it works | v1? |
|---|---|---|
| Public page link | Generates an unguessable token URL (`/share/{token}`). Renders the page as read-only markdown, no editor chrome. Optional expiry (24h / 7d / 30d / never). Revocable. | Yes |
| Query result link | Shares a specific query + its frozen answer as a permalink. Answer is captured at share time and does not update if the wiki changes. | Yes |
| Export as PDF | `GET /api/export?slugs=page-slug&format=pdf`. Server-side render via WeasyPrint. Single or multi-page. | Yes |
| Export as HTML | Static self-contained HTML bundle. Internal wikilinks resolved to anchors. Can be emailed or published anywhere. | Yes |
| Wiki invite (viewer) | Owner generates an invite link from Settings → Users. Guest clicks, sets a password, gets viewer access. | Yes |
| Wiki invite (collaborator) | Same flow, owner selects "collaborator" role. Guest gets read + write but not ingest or admin. | Yes |
| Share with expiry | All share links can optionally auto-expire. Owner can revoke any link at any time from Settings → Share links. | Yes |
| Public wiki | Making an entire wiki world-readable without a share token. | Yes |
| Granular page permissions | Restricting individual pages within a wiki to specific users. | Yes |

### Share Link Implementation

```
Share token format:  /share/{32-byte-url-safe-base64-token}
Stored in:           share_links table in SQLite (swappable to Postgres for larger deployments)
Fields:              token, type (page|query), target_id, created_at, expires_at, revoked
Served by:           Cloudflare Tunnel subdomain for external access
                     Direct on Tailscale network for trusted users
```

Share links are served by a lightweight read-only renderer — they do not have access to the editor, search, graph, or any write endpoints.

## 12. Design & UX Requirements

### Layout

Three-panel layout:

```
┌─────────────┬──────────────────────────┬──────────────────┐
│ File sidebar│   Editor / active view   │  Backlinks /     │
│ (collapsible│   (CodeMirror 6 or       │  context panel   │
│ folder tree)│   graph / query / search)│                  │
└─────────────┴──────────────────────────┴──────────────────┘
```

### CodeMirror 6 Extensions

| Extension | Behaviour |
|---|---|
| `[[wikilink]]` | Custom CM6 extension — autocomplete, navigation, broken-link detection |
| Markdown highlighting | Headings, bold, italic, code blocks, frontmatter |
| Live preview split | Toggle editor-only / split / preview-only |
| Auto-save | Debounced 1s save via WebSocket |
| Frontmatter | YAML block highlighted and parsed |

---

## 13. Timeline & Milestones

| Day | Focus | Deliverable |
|---|---|---|
| 1 | Infrastructure | `docker-compose.yml` boots all services; Qdrant + Neo4j clients wired; FastAPI skeleton; auth (owner login, JWT cookies) |
| 2 | Core ingest | `.md`, `.pdf`, `.txt`, `.html`, URL → LLM extract → markdown → Qdrant → Neo4j; ingest panel with live progress |
| 3 | Editor + file tree | CodeMirror 6 with markdown highlighting, `[[wikilink]]` autocomplete, auto-save; file sidebar; backlinks panel |
| 4 | Extended ingest + graph | `.docx`, `.pptx`, `.xlsx`, `.csv`, `.json`, `.epub`, code files; graph view (vis.js on Neo4j) |
| 5 | Query + search + sharing | Query chat (streaming SSE); semantic search; share links; wiki invites; PDF + HTML export |
| 6 | MCP + security | MCP server (stdio + SSE, all 8 tools, Inspector validated); CSP, rate limiting, CSRF, markdown sanitisation |
| 7 | Stretch + ship | Image/audio/video ingest if time allows; end-to-end testing; README with MCP client config snippets; first real bulk ingest |

**Cut order if falling behind:** Day 7 stretch ingest → graph view → share links → extended parsers. Irreducible core: ingest (.md/.pdf) + editor + query + MCP.

---

## 14. Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Neo4j too heavy for home server | M | H | Test on Day 1. Fallback: Kuzu (embedded graph DB, much lighter) |
| CM6 `[[wikilink]]` extension takes too long | M | M | Scope down to highlighting without autocomplete for v1 if needed |
| LLM ingest quality poor | M | H | Invest in prompt engineering Day 2 with real test sources |
| stdio transport config too complex for users | M | M | Ship copy-paste config snippets for every major client in README |
| One-week timeline too tight | H | M | Irreducible core: ingest + editor + MCP. Graph view is the first cut. |
| Future multi-tenancy rewrite | L | H | `wiki_id` on all models from day 1 |

---

## 15. Marketing Plan

### Positioning

Archivum sits at the intersection of three trends that all have large, frustrated audiences:

1. **Obsidian users who won't pay for Sync** — large subreddit (r/ObsidianMD, 200k+ members), vocal about the sync paywall, actively searching for alternatives
2. **Developers building with MCP** — fastest-growing segment of the agent tooling ecosystem right now
3. **People burned by RAG** — researchers and devs who've tried NotebookLM/RAG and found it doesn't compound

The message is simple: *Obsidian, but free, self-hosted, and the AI does all the filing.*

### Channels

**Reddit (launch week)**
- r/ObsidianMD — "I built a self-hosted Obsidian alternative with a built-in AI agent that maintains the wiki for you. No sync paywall. Open source."
- r/selfhosted — focus on the Docker angle, home server audience
- r/LocalLLaMA — focus on Ollama support and air-gapped operation
- r/ClaudeAI and r/ChatGPT — focus on MCP server, agent use case

**Hacker News**
- "Show HN: Archivum – self-hosted wiki where the LLM does the bookkeeping"
- Lead with the Memex reference (Vannevar Bush) — HN loves this framing
- Have a working demo GIF ready; HN is unforgiving of vaporware

**GitHub**
- Good README is the best marketing for this audience
- Include: one-command deploy, architecture diagram, client config snippets for every MCP client
- Submit to `awesome-selfhosted`, `awesome-mcp-servers`, and Glama MCP registry
- Star-seeking is legitimate: post to GitHub trending topics, ask early users to star

**Twitter/X and Bluesky**
- Short demo video: drag in a PDF, watch the graph grow, ask a question, get a cited answer
- Tag Obsidian, mention the sync paywall frustration — this reliably gets engagement from their userbase
- Developer audience on Bluesky is growing; cross-post both

**YouTube / short video**
- A 90-second screen recording beats any written explanation for this product
- Show the full loop: upload → graph grows → query → answer with citations
- Upload to YouTube, embed in README and HN post

### MCP Registry Distribution

Submit to these registries on launch day — they drive passive discovery from users already looking for MCP tools:

- **Glama** (glama.ai/mcp/servers) — largest MCP registry, 22k+ servers listed
- **mcp.so** — curated directory, higher signal
- **Awesome MCP Servers** (GitHub list) — open a PR
- **Anthropic's MCP servers page** — submit via their contribution process

### Messaging by Audience

| Audience | Lead message |
|---|---|
| Obsidian users | "Obsidian without the sync paywall. The AI maintains the wiki for you." |
| Self-hosters | "One `docker compose up`. Everything local. No cloud dependency." |
| Developers / Claude Code users | "An MCP server for your personal knowledge base. Works with Claude Code, Cursor, Windsurf, everything." |
| Researchers | "Your research compiles itself. Stop re-deriving the same synthesis every time you ask a question." |
| HN / technical audience | "A persistent wiki maintained by an LLM — the Memex that Vannevar Bush couldn't build." |

### Future Product Distribution

Distribution targets:
- Docker Hub public image (`archivumapp/archivum`) — passive discovery from Docker users
- GitHub Container Registry (`ghcr.io/archivum/archivum`) — preferred by self-hosters
- Coolify / Caprover one-click template — reaches the "managed self-hosted" segment
- Unraid Community Apps — large home server community
- Umbrel App Store — growing home server OS with an app marketplace

---

## 16. Dependencies & Assumptions

### Dependencies

- Docker and Docker Compose on the home server
- Anthropic API key (or Ollama locally)
- 4GB+ RAM available (Neo4j recommends 2GB alone)

### Assumptions

- Single user in v1 — last-write-wins is acceptable
- LAN access is sufficient for v1
- Markdown is the right canonical format
- LLM is good enough at entity extraction without fine-tuning — validate Day 2

---

## 17. Open Questions

| Question | Owner | Due | Status |
|---|---|---|---|
| vis.js vs Sigma.js — performance at 500+ nodes? | Builder | Day 3 | Open |
| `[[wikilinks]]` use page slug or title as identifier? | Builder | Day 2 | Open |
| Default embedding model — Anthropic API or local Ollama? | Builder | Day 1 | Open |
| Neo4j vs Kuzu — acceptable RAM footprint on target hardware? | Builder | Day 1 | Open |
| Chunking strategy for long pages — whole page or sliding window? | Builder | Day 2 | Open |
| Docker Hub org name — `archivum` or `archivumapp`? | Builder | Post-v1 | Open |
| Domain — `archivumapp.com` (register when ready to launch)? | Builder | Post-v1 | Open |
