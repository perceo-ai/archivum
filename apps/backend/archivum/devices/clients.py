"""What Archivum knows about the agents that connect to it.

This is data, not code, and it is served rather than compiled in. A client
writer living in the CLI means supporting a new agent needs a CLI release and
every machine re-running an installer. Served from here, adding one is an edit
to this file that every machine picks up the next time it links.

Each entry says how to recognise the client, where its config lives, what shape
to merge in, and — for session capture — where it writes transcripts. The CLI
is a generic executor of these; it holds no per-client knowledge.
"""

from __future__ import annotations

from typing import Any

# Bumped when the shape of an entry changes, not when an entry is added. A CLI
# that does not understand the shape should say so rather than write a config
# it half-understands into a file another tool owns.
REGISTRY_VERSION = 1

# Transport per client, which is not cosmetic: the MCP port serves `/sse` and
# `/mcp` from one app, and a streamable-HTTP client pointed at `/sse` fails to
# start with 405 Method Not Allowed rather than degrading.
_SSE = "sse"
_STREAMABLE = "streamable-http"


def _clients() -> list[dict[str, Any]]:
    return [
        {
            "id": "claude",
            "label": "Claude Code",
            # `claude mcp add` is the supported way in. `~/.claude.json` is
            # Claude Code's live state file, so writing it behind a running
            # app risks losing whatever that app flushes next.
            "detect": [".claude.json", ".claude"],
            "method": "command",
            "command": [
                "claude", "mcp", "add", "--scope", "user",
                "--transport", "sse", "archivum", "{url}",
                "--header", "Authorization: Bearer {key}",
            ],
            "fallback": {
                "method": "json",
                "path": "~/.claude.json",
                "key_path": ["mcpServers", "archivum"],
            },
            "transport": _SSE,
            "skill_dir": "~/.claude/skills",
            "transcripts": ["~/.claude/projects"],
        },
        {
            "id": "cursor",
            "label": "Cursor",
            "detect": [".cursor"],
            "method": "json",
            "path": "~/.cursor/mcp.json",
            "key_path": ["mcpServers", "archivum"],
            "transport": _SSE,
            "transcripts": [],
        },
        {
            "id": "codex",
            "label": "Codex",
            "detect": [".codex"],
            "method": "toml",
            "path": "~/.codex/config.toml",
            "key_path": ["mcp_servers", "archivum"],
            "transport": _STREAMABLE,
            "transcripts": ["~/.codex/sessions"],
        },
        {
            "id": "hermes",
            "label": "Hermes Agent",
            "detect": [".hermes"],
            "method": "yaml",
            "path": "~/.hermes/config.yaml",
            "key_path": ["mcp_servers", "archivum"],
            "transport": _STREAMABLE,
            # Hermes interpolates ${env:VAR} anywhere in a server entry and
            # reads ~/.hermes/.env, so the key goes there and the config holds
            # a reference. One fewer file with a live credential in it.
            "env_file": "~/.hermes/.env",
            "env_var": "ARCHIVUM_KEY",
            "transcripts": ["~/.hermes/sessions"],
        },
        {
            "id": "openclaw",
            "label": "OpenClaw",
            "detect": [".openclaw"],
            "method": "json",
            # Sources disagree: ~/.openclaw/openclaw.json with a top-level
            # `mcpServers` key, versus .openclaw/config.json with nested
            # `mcp.servers`. Confirm against an install before trusting this;
            # being a served entry is what makes correcting it a data change
            # rather than a release.
            "path": "~/.openclaw/openclaw.json",
            "key_path": ["mcpServers", "archivum"],
            "transport": _STREAMABLE,
            "unverified": True,
            "transcripts": [],
        },
    ]


# Clients configured in a browser, which cannot run an installer and so are
# never "detected". They are listed so Settings can show a copy-paste panel
# built from the same source as everything else.
def _web_clients() -> list[dict[str, Any]]:
    return [
        {
            "id": "claude-web",
            "label": "claude.ai",
            "method": "manual",
            "transport": _STREAMABLE,
            "instructions": (
                "Settings → Connectors → Add custom connector. Paste the URL, "
                "then add an Authorization header with the key."
            ),
        },
        {
            "id": "chatgpt",
            "label": "ChatGPT",
            "method": "manual",
            "transport": _STREAMABLE,
            "instructions": (
                "Settings → Connectors → Add. Paste the URL and the "
                "Authorization header."
            ),
        },
    ]


def client_registry(*, sse_url: str, streamable_url: str) -> dict[str, Any]:
    """The manifest a linking machine fetches, with URLs already resolved.

    Resolving the URL here rather than in the CLI is deliberate: the server is
    the only party that knows whether it sits behind a reverse proxy, and a
    client that guesses writes its own hostname into a config that then names
    the wrong machine.
    """
    return {
        "version": REGISTRY_VERSION,
        "urls": {_SSE: sse_url, _STREAMABLE: streamable_url},
        "clients": _clients(),
        "web_clients": _web_clients(),
    }


def transcript_dirs() -> dict[str, list[str]]:
    """Where each client writes sessions, for the capture watcher.

    Kept on the same entries as the config paths so the two cannot drift: a
    client added for configuration is a client capture already knows about.
    """
    return {c["id"]: c.get("transcripts", []) for c in _clients()}
