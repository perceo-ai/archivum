# Agent setup: the whole UX

Every path a person or an agent can take through setup, indexing, and capture.
Written to be audited: each box names the real route or file, so a claim here is
checkable against the code rather than taken on trust.

Routes are given in full. Router prefixes are `/api/mcp` (devices), `/api/repos`,
`/api/sources` (capture), and none (installer).

## 1. The whole picture

Three planes. The dashed line is the one that used to be impossible: the server
cannot read any client machine's disk, so everything crossing it is pushed by
the client rather than pulled by the server.

```mermaid
flowchart LR
    subgraph browser["Your browser"]
        settings["Settings, Agent Access"]
        webc["claude.ai / ChatGPT<br/>connector, paste URL + header"]
    end

    subgraph machines["Machines you code on"]
        install["curl /install | sh"]
        cli["archivum CLI<br/>~/.archivum/cli"]
        agents["Claude Code, Cursor, Codex,<br/>Hermes, OpenClaw"]
        repo["Your repository"]
        transcripts["Agent transcripts<br/>~/.claude/projects"]
    end

    subgraph server["Your server"]
        api["REST API :8473"]
        mcp["MCP :8001<br/>/sse and /mcp"]
        vault[("Markdown vault,<br/>Qdrant, Kuzu, SQLite")]
    end

    settings -->|"issue arch1p_ token"| install
    settings -->|"mint amk_ key"| webc
    install --> cli
    cli -->|"writes config"| agents
    cli -->|"archivum index"| api
    cli -->|"archivum watch"| api
    repo --> cli
    transcripts --> cli
    agents -->|"MCP tools, Bearer amk_"| mcp
    webc -->|"Bearer amk_"| mcp
    api --- vault
    mcp --- vault

    linkStyle 4,5 stroke-dasharray: 5 5
```

## 2. Linking a machine

The zero-touch path. The only input is one environment variable; everything
else the machine needs travels inside it or is fetched from the server.

```mermaid
sequenceDiagram
    autonumber
    actor A as Agent on a new machine
    participant S as Your server
    participant C as Client configs

    Note over A: ARCHIVUM_PROVISION_TOKEN=arch1p_...<br/>The token carries the server URL

    A->>S: GET /install
    S-->>A: shell script, server URL baked in
    A->>S: GET /install/cli.tar.gz
    S-->>A: dependency-free CLI, deterministic bytes
    Note over A: installs to ~/.archivum/cli,<br/>links ~/.local/bin/archivum

    A->>S: POST /api/mcp/pairing/provision<br/>secret + device_name + fingerprint
    Note over S: cap checked, fingerprint replaces<br/>this machine's previous key
    S-->>A: amk_ device key + sse_url + mcp_url

    A->>S: GET /api/mcp/clients (Bearer amk_)
    S-->>A: manifest: paths, formats, transports,<br/>transcript dirs

    loop each detected client
        A->>C: write config from the manifest entry
    end
    Note over C: clients that resolve env vars get<br/>${env:ARCHIVUM_KEY}, not the key itself

    A->>S: GET /api/mcp/skill
    S-->>A: archivum-memory SKILL.md

    A->>S: GET sse_url (Bearer amk_)
    S-->>A: 200
    Note over A: refuses to report success<br/>for an endpoint nobody has spoken to
```

## 3. What each credential can do

The centrepiece of the audit. Three credential classes, deliberately unequal.

```mermaid
flowchart TD
    owner["Owner session (JWT)<br/>browser login"]
    prov["Provisioning token arch1p_<br/>lives in a shell profile"]
    dev["Device key amk_<br/>one per machine"]
    legacy["Legacy MCP_API_KEY<br/>shared, being retired"]

    owner --> o1["issue and revoke tokens"]
    owner --> o2["mint a key for a web client"]
    owner --> o3["read and write the vault"]
    owner --> o4["register a server-side path"]

    prov --> p1["mint device keys<br/>POST /api/mcp/pairing/provision"]
    prov --> p2["nothing else"]

    dev --> d1["every MCP tool"]
    dev --> d2["upload a repo<br/>POST /api/repos/upload"]
    dev --> d3["upload a transcript<br/>POST /api/sources/capture/upload"]
    dev --> d4["read and revoke itself<br/>/api/mcp/devices/self"]

    legacy --> d1

    prov -.->|"refused by prefix before<br/>the legacy comparison"| d1

    style p2 fill:#f9f2f4
    style prov fill:#fff3cd
```

The dotted edge is the property the key class exists for: `arch1p_` is rejected
in `DeviceBearerTokenVerifier.verify_token` *before* the constant-time legacy
comparison, so pasting one into `MCP_API_KEY` cannot turn a mint-only secret
into a read-everything one.

## 4. Indexing a repository

```mermaid
sequenceDiagram
    autonumber
    actor U as You, in a repo
    participant CLI as archivum index
    participant S as Server
    participant P as Existing index pipeline

    U->>CLI: archivum index
    CLI->>CLI: git ls-files -co --exclude-standard
    Note over CLI: .gitignore honoured by asking git,<br/>not by reimplementing it
    CLI->>CLI: drop binaries (NUL byte), >2MB, symlinks
    CLI->>CLI: tar -czf
    CLI->>S: POST /api/repos/upload (Bearer amk_)

    rect rgb(255, 243, 205)
        Note over S: extraction refuses, never sanitises
        S->>S: absolute paths, .. traversal, symlinks,<br/>hard links, device nodes, gzip bombs,<br/>member count
    end

    S->>S: replace staging tree (not merge)
    S->>P: index_repo, unchanged
    P-->>S: files, symbols, edges, pages
    S-->>CLI: repo summary
    Note over U: retrieve_code_context and recall_fix<br/>now answer for this repo, from every<br/>machine you have linked
```

A refused archive leaves nothing behind. Replacing rather than merging is what
stops a file deleted since the last upload from surviving in the index.

## 5. Capturing sessions

```mermaid
sequenceDiagram
    autonumber
    participant W as archivum watch
    participant F as Transcript files
    participant S as Server
    participant I as Existing importers

    loop every 60s, or --once
        W->>F: scan dirs named by the client registry
        W->>W: skip unchanged (size + mtime)

        rect rgb(255, 243, 205)
            Note over W: redaction, before anything leaves
            W->>W: sk-, sk-ant-, ghp_, xox, AIza, AKIA,<br/>amk_, arch1_, arch1p_, PEM blocks,<br/>KEY=value assignments
        end

        W->>S: POST /api/sources/capture/upload (Bearer amk_)
        S->>I: connector_for, then parse
        I-->>S: conversations
        S->>S: CaptureStore, content-addressed
        Note over S: unchanged transcript dedupes<br/>instead of duplicating
        S-->>W: result
        W->>W: record as seen, success or failure
    end
```

Redaction is a set of shapes, not a guarantee. A secret that looks like prose
survives. Nothing starts this watcher automatically; it is opt-in per machine.

## 6. Revoking

Two different problems, two different answers, which is why there are two
buttons rather than one.

```mermaid
flowchart TD
    start{"What happened?"}

    start -->|"routine rotation"| rot["DELETE /api/mcp/provisioning-tokens/ID"]
    rot --> rot1["token stops minting"]
    rot --> rot2["every machine it linked<br/>keeps working"]

    start -->|"the token leaked"| leak["DELETE ...?revoke_devices=true"]
    leak --> leak1["token stops minting"]
    leak --> leak2["every key it ever minted<br/>is revoked too"]

    start -->|"lost one laptop"| one["DELETE /api/mcp/devices/ID"]
    one --> one1["that machine only"]

    start -->|"decommissioning<br/>a machine you hold"| self["archivum connect --revoke"]
    self --> self1{"server confirms?"}
    self1 -->|yes| self2["key revoked, local record deleted"]
    self1 -->|no| self3["local record kept<br/>so you still know what to revoke"]

    style leak fill:#f8d7da
    style self3 fill:#fff3cd
```

## 7. What an agent does with it

```mermaid
flowchart TD
    task["Agent picks up a task"]
    task --> indexed{"list_repositories<br/>knows this repo?"}
    indexed -->|no| doindex["index_repository, or<br/>archivum index from this machine"]
    doindex --> err{"path on<br/>this server?"}
    err -->|no| hint["error names the fix:<br/>'archivum index PATH'"]
    err -->|yes| indexed
    indexed -->|yes| work

    work{"What kind of work?"}
    work -->|"an error"| recall["recall_fix(symptom)"]
    recall --> hit{"seen before?"}
    hit -->|yes| apply["diagnosis, files changed,<br/>how it was verified, cited"]
    hit -->|no| new["says so plainly:<br/>new trouble, worth recording"]

    work -->|"unfamiliar code"| ctx["retrieve_code_context(query, repo)"]
    ctx --> gnav["graph_neighbors,<br/>graph_shortest_path"]

    apply --> done
    new --> done
    gnav --> done
    done["Work finished"] --> rec["record_work: request, outcome,<br/>cause, changed_paths, verified_by"]
    rec --> stream["appears in your stream,<br/>reviewable and citable"]
```

The `list_repositories` check at the top is what the skill now leads with. It
used to gate itself on the repository already being indexed, which at zero
repositories was permanently false, so it never ran and nothing was ever
indexed.

## 8. Where each surface lives

| Surface | Where | Auth |
|---|---|---|
| Issue, list, revoke provisioning tokens | Settings, Agent Access | owner |
| Link a device (pairing token) | Settings, Agent Access | owner |
| Mint a key for a browser connector | Settings, Agent Access | owner |
| Installer and CLI download | `GET /install`, `/install.ps1`, `/install/cli.tar.gz` | none, public code |
| Redeem a provisioning secret | `POST /api/mcp/pairing/provision` | the secret itself |
| Client manifest | `GET /api/mcp/clients` | device |
| Skill | `GET /api/mcp/skill` | none |
| Upload a repository | `POST /api/repos/upload` | device |
| Upload a transcript | `POST /api/sources/capture/upload` | device |
| Self status and self-revoke | `GET`/`DELETE /api/mcp/devices/self` | device |
| MCP tools | `:8001/sse` and `:8001/mcp` | device or legacy key |

## Known gaps

- OpenClaw's config path is seeded from documentation and flagged `unverified`
  in the registry. Sources disagree between `~/.openclaw/openclaw.json` with a
  top-level `mcpServers` key and `.openclaw/config.json` with nested
  `mcp.servers`. Confirm against an install; correcting it is a data edit.
- An uploaded tree carries no git history, so `since_sha` incremental indexing
  does not apply and each `archivum index` is a full reindex.
- Browser connectors need the vault reachable over public HTTPS. The Settings
  panel says so rather than leaving it to be discovered as a connector that
  never works.
