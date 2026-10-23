"""Repositories as first-class memory.

Archivum is a second brain for someone who writes code, so a repository is not
an import target — it is one of the things being remembered. Archgraph could
already read a repo into canonical knowledge, but the only way to run it was a
console script that no route, tool or screen called, and it wrote its lexical
index into a database inside the repo that the server never opened. The graph
existed; nothing could reach it.

This module is the application-facing half: register a repo, index it on a
queue, and leave behind the same kinds of record every other memory leaves —
canonical objects, a governed asset, and editable markdown in the vault.

Indexing is queued rather than inline because parsing a repository is slow and
CPU-bound, and the wiki has to stay responsive while it happens. That is the
same reason distillation runs on a queue.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiosqlite

from archivum.archgraph.ingest import ingest_repo
from archivum.archgraph.repo import snapshot_repo
from archivum.code_pages import repo_folder, write_repo_pages
from archivum.config import Settings, get_settings
from archivum.db import sqlite
from archivum.knowledge.personal_root import ensure_personal_root
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.memory.catalog import register_codegraph_asset
from archivum.memory.registry import MemoryAssetRegistry

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS code_repos (
    scope        TEXT PRIMARY KEY,
    wiki_id      TEXT NOT NULL,
    name         TEXT NOT NULL,
    path         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    last_sha     TEXT,
    files        INTEGER NOT NULL DEFAULT 0,
    nodes        INTEGER NOT NULL DEFAULT 0,
    edges        INTEGER NOT NULL DEFAULT 0,
    pages        INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    indexed_at   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_code_repos_wiki ON code_repos(wiki_id);
"""


class RepoError(Exception):
    """The repository cannot be indexed as asked."""


@dataclass(frozen=True)
class CodeRepo:
    scope: str
    wiki_id: str
    name: str
    path: str
    status: str
    last_sha: str | None
    files: int
    nodes: int
    edges: int
    pages: int
    error: str | None
    indexed_at: str | None


def _row_to_repo(row: Any) -> CodeRepo:
    return CodeRepo(
        scope=row["scope"],
        wiki_id=row["wiki_id"],
        name=row["name"],
        path=row["path"],
        status=row["status"],
        last_sha=row["last_sha"],
        files=row["files"],
        nodes=row["nodes"],
        edges=row["edges"],
        pages=row["pages"],
        error=row["error"],
        indexed_at=row["indexed_at"],
    )


REPO_SCOPE_PREFIX = "repo:"

# A repository name becomes a directory under the cache root and a folder in the
# vault, so it has to be a single safe path segment. Without this a name
# containing traversal or an absolute path would place generated files anywhere
# the backend could reach.
_SAFE_REPO_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_REPO_NAME_LENGTH = 100

# Code records are short — a name, a signature, a summary — so a repository
# affords more of them per package than prose memory does.
CODE_SCOPE_BUDGET_TOKENS = 8000
CODE_SCOPE_BUDGET_ITEMS = 40


def validate_repo_name(name: str) -> str:
    """Return `name` if it is safe to use as a path segment, else raise."""
    candidate = name.strip()
    if not candidate or len(candidate) > _MAX_REPO_NAME_LENGTH:
        raise RepoError("A repository name must be 1–100 characters")
    if not _SAFE_REPO_NAME.match(candidate) or candidate in {".", ".."}:
        raise RepoError(
            "A repository name may only contain letters, digits, dot, dash and "
            "underscore, and may not contain a path separator"
        )
    return candidate


_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _name_segment(value: str) -> str:
    return _UNSAFE_NAME_CHARS.sub("-", value).strip("-._")


def _remote_parts(url: str) -> tuple[str, str, str] | None:
    """(host, owner, repo) from a remote URL in https, ssh or scp form, else None.

    Any host: the last two path segments are the owner and the repository.
    """
    url = url.strip()
    if "://" in url:
        parts = urlsplit(url)
        host, path = parts.hostname or "", parts.path
    elif ":" in url.split("/", 1)[0]:
        authority, path = url.split(":", 1)  # git@host:owner/repo.git
        host = authority.rsplit("@", 1)[-1]
    else:
        host, path = "", url
    segments = [segment for segment in re.split(r"[/\\]", path) if segment]
    if len(segments) < 2:
        return None
    return host.lower(), segments[-2].lower(), segments[-1].removesuffix(".git").lower()


def _identity_from_parts(parts: tuple[str, str, str] | None) -> str | None:
    if parts is None:
        return None
    owner, repo = _name_segment(parts[1]), _name_segment(parts[2])
    if not owner or not repo:
        return None
    try:
        return validate_repo_name(f"{owner}-{repo}"[:_MAX_REPO_NAME_LENGTH])
    except RepoError:
        return None


def _identity_from_remote_url(url: str) -> str | None:
    """`owner-repo` from a remote URL, lowercased and safe as a path segment."""
    return _identity_from_parts(_remote_parts(url))


def _git(path: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _git_remote_parts(path: Path) -> tuple[str, str, str] | None:
    """Where `path`'s origin remote points, if `path` is the top of a working tree.

    Only the top: `git -C` happily answers from inside a subdirectory, and two
    subdirectories of one monorepo indexed on their own would otherwise both
    take the monorepo's name and overwrite each other.
    """
    toplevel = _git(path, "rev-parse", "--show-toplevel")
    if toplevel is None or Path(toplevel).resolve() != path:
        return None
    url = _git(path, "remote", "get-url", "origin")
    return _remote_parts(url) if url else None


def _git_remote_identity(path: Path) -> str | None:
    """The repository's name as its origin remote has it, or None.

    The checkout directory's name says where a clone sits, not what it is: a
    repository cloned into `nixos` was remembered as `nixos`, and every repo
    checked out under a same-named directory collided into one namespace.
    """
    return _identity_from_parts(_git_remote_parts(path))


async def _name_from_remote(path: Path, *, wiki_id: str) -> str | None:
    """The remote-derived name for `path`, kept apart from any other repository.

    `owner-repo` is not unique: `acme-tools/widget` and `acme/tools-widget`
    both read `acme-tools-widget`, and pages go to the slug of the name, which
    folds more together still. When another registered checkout already holds
    that folder and is a different repository — its remote differs, or it has
    none — this one takes a short hash of its remote as a suffix. A checkout
    already registered keeps the name it has, so its pages never move.
    """
    parts = _git_remote_parts(path)
    name = _identity_from_parts(parts)
    if parts is None or name is None:
        return None
    digest = hashlib.sha1("/".join(parts).encode("utf-8")).hexdigest()[:8]
    suffixed = validate_repo_name(f"{name[: _MAX_REPO_NAME_LENGTH - 9]}-{digest}")

    repos = await list_repos(wiki_id=wiki_id)
    for repo in repos:
        if Path(repo.path) == path and repo.name in {name, suffixed}:
            return repo.name
    folder = repo_folder(name)
    for repo in repos:
        other = Path(repo.path)
        # A checkout that is gone cannot be compared; treat it as this one,
        # moved, so re-cloning somewhere new keeps the same namespace.
        if repo_folder(repo.name) != folder or other == path or not other.is_dir():
            continue
        if _git_remote_parts(other) != parts:
            return suffixed
    return name


def scope_for(name: str, *, wiki_id: str) -> str:
    """The canonical scope for one vault's copy of a repository.

    The vault id is part of the scope because `api` or `web` is a name many
    vaults will use. Keying on the name alone meant the second vault to register
    took over the first vault's register row, and both vaults' code records
    landed in one shared scope in canonical knowledge.
    """
    return f"{REPO_SCOPE_PREFIX}{wiki_id}:{name}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def init_repo_schema(conn: aiosqlite.Connection) -> None:
    await conn.executescript(SCHEMA)


# ── Registry ──────────────────────────────────────────────────────────────────


async def register_repo(*, path: Path, wiki_id: str, name: str | None = None) -> CodeRepo:
    """Record a repository and queue it for indexing.

    The path is resolved and checked here rather than in the worker so the
    person registering it finds out immediately that they typed it wrong.
    """
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        # Almost always a path on the caller's machine rather than a typo: this
        # route resolves paths on the server, and the server cannot see a
        # laptop's disk. Saying only "not a directory" sends people hunting for
        # a mistake they did not make, so name the actual fix.
        raise RepoError(
            f"'{path}' is not a directory on this server. If that path is on "
            "another machine, index it from there instead: `archivum index "
            f"{path}` uploads the repository and indexes it here."
        )

    repo_name = validate_repo_name(
        name or await _name_from_remote(resolved, wiki_id=wiki_id) or resolved.name
    )

    scope = scope_for(repo_name, wiki_id=wiki_id)
    now = _now()
    async with sqlite.get_db() as conn:
        await init_repo_schema(conn)
        await conn.execute(
            """
            INSERT INTO code_repos (scope, wiki_id, name, path, status, created_at, updated_at)
            VALUES (?,?,?,?, 'pending', ?, ?)
            ON CONFLICT(scope) DO UPDATE SET
                path=excluded.path,
                status='pending',
                error=NULL,
                updated_at=excluded.updated_at
            WHERE code_repos.wiki_id = excluded.wiki_id
            """,
            (scope, wiki_id, repo_name, str(resolved), now, now),
        )
        await conn.commit()
    repo = await get_repo(scope, wiki_id=wiki_id)
    assert repo is not None
    return repo


async def list_repos(*, wiki_id: str) -> list[CodeRepo]:
    async with sqlite.get_db() as conn:
        await init_repo_schema(conn)
        async with conn.execute(
            "SELECT * FROM code_repos WHERE wiki_id=? ORDER BY name ASC", (wiki_id,)
        ) as cursor:
            return [_row_to_repo(row) for row in await cursor.fetchall()]


async def get_repo(scope: str, *, wiki_id: str) -> CodeRepo | None:
    async with sqlite.get_db() as conn:
        await init_repo_schema(conn)
        async with conn.execute(
            "SELECT * FROM code_repos WHERE scope=? AND wiki_id=?", (scope, wiki_id)
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_repo(row) if row else None


async def owned_repo_scopes(*, wiki_id: str) -> set[str]:
    """The repo scopes this wiki may read.

    Code lives outside the `wiki:` namespace, so authorisation cannot be derived
    from the scope string the way it can for pages. It is derived from the
    register instead: you may read a repo you registered.
    """
    return {repo.scope for repo in await list_repos(wiki_id=wiki_id)}


async def _set_status(scope: str, status: str, **fields: Any) -> None:
    assignments = ["status=?", "updated_at=?"]
    params: list[Any] = [status, _now()]
    for key, value in fields.items():
        assignments.append(f"{key}=?")
        params.append(value)
    params.append(scope)
    async with sqlite.get_db() as conn:
        await init_repo_schema(conn)
        await conn.execute(
            f"UPDATE code_repos SET {', '.join(assignments)} WHERE scope=?", params
        )
        await conn.commit()


# ── Indexing ──────────────────────────────────────────────────────────────────


async def index_repo(repo: CodeRepo, *, settings: Settings | None = None) -> CodeRepo:
    """Read one repository into canonical knowledge, memory, and the vault."""
    settings = settings or get_settings()
    root = Path(repo.path)
    if not root.is_dir():
        raise RepoError(f"'{repo.path}' is no longer a directory on this server")

    # `repo.name` was validated as a single safe path segment at registration;
    # resolving and re-checking keeps that guarantee local to the write.
    cache_root = settings.code_cache_dir.resolve()
    cache_dir = (cache_root / validate_repo_name(repo.name)).resolve()
    if not cache_dir.is_relative_to(cache_root):
        raise RepoError(f"Cache path for '{repo.name}' escapes the cache root")
    cache_dir.mkdir(parents=True, exist_ok=True)

    update = repo.last_sha is not None
    current_sha = snapshot_repo(root).commit_sha
    # This vault's memory and its other repositories, so a symbol can reach a
    # decision and two repos can recognise a shared type — and nothing beyond.
    related = {f"wiki:{repo.wiki_id}"} | await owned_repo_scopes(wiki_id=repo.wiki_id)

    async with sqlite.get_db() as conn:
        await init_knowledge_schema(conn)
        knowledge = KnowledgeRepository(conn)
        # One connection for canonical knowledge and the lexical projection.
        # They used to live in different files, which is why code retrieval
        # could never find its own index.
        report = await ingest_repo(
            root,
            scope=repo.scope,
            cache_dir=cache_dir,
            knowledge=knowledge,
            lexical_conn=conn,
            update=update,
            since_sha=repo.last_sha if update else None,
            # Derived links may only reach this repository and the vault that
            # owns it — never another tenant's memory.
            related_scopes=related,
        )
        await ensure_personal_root(knowledge, wiki_id=repo.wiki_id)
        # Budgets live in the scope registry, so a scope with no row is
        # unbounded — the budget system simply did not apply to code.
        await MemoryAssetRegistry(conn).upsert_scope(
            id=repo.scope,
            wiki_id=repo.wiki_id,
            scope_type="repo",
            name=repo.name,
            budget_tokens=CODE_SCOPE_BUDGET_TOKENS,
            budget_items=CODE_SCOPE_BUDGET_ITEMS,
        )
        await register_codegraph_asset(
            MemoryAssetRegistry(conn),
            knowledge,
            wiki_id=repo.wiki_id,
            repo_scope=repo.scope,
            change_note="Indexed from the repository",
        )
        await conn.commit()

    pages = await write_repo_pages(repo, settings=settings)

    await _set_status(
        repo.scope,
        "ready",
        last_sha=None if current_sha == "working-tree" else current_sha,
        files=report.files,
        nodes=report.nodes,
        edges=report.edges,
        pages=pages,
        error=None,
        indexed_at=_now(),
    )
    updated = await get_repo(repo.scope, wiki_id=repo.wiki_id)
    assert updated is not None
    return updated


async def run_pending_repo_indexing(
    *, settings: Settings | None = None, limit: int = 4
) -> int:
    """Index up to `limit` queued repositories. Returns how many were indexed."""
    settings = settings or get_settings()
    async with sqlite.get_db() as conn:
        await init_repo_schema(conn)
        async with conn.execute(
            "SELECT * FROM code_repos WHERE status='pending' ORDER BY updated_at ASC LIMIT ?",
            (limit,),
        ) as cursor:
            pending = [_row_to_repo(row) for row in await cursor.fetchall()]

    done = 0
    for repo in pending:
        await _set_status(repo.scope, "indexing")
        try:
            await index_repo(repo, settings=settings)
        except Exception as exc:  # noqa: BLE001 - one bad repo must not stop the rest
            logger.warning("Indexing %s failed: %s", repo.scope, exc)
            await _set_status(repo.scope, "error", error=f"{type(exc).__name__}: {exc}")
            continue
        done += 1
    return done


async def run_code_repo_worker(settings: Settings) -> None:
    """Drain the repository queue for the lifetime of the process."""
    interval = max(settings.code_repo_worker_interval_seconds, 1)
    logger.info("Code repository worker started", extra={"interval_s": interval})
    while True:
        try:
            await asyncio.sleep(interval)
            await run_pending_repo_indexing(settings=settings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad pass must not stop the pump
            logger.warning("Code repository sweep failed: %s", exc)
