"""archgraph.hook — CLI entrypoint and git post-commit hook installer.

The CLI stores the extracted code graph in the canonical knowledge repository.
Canonical records live in ``<repo>/.archivum/knowledge.db``. The SQLite lexical
index in ``<cache_dir>/index.db`` remains a rebuildable projection used for
deterministic code retrieval.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import aiosqlite

from archivum.archgraph.ingest import IngestReport, ingest_repo
from archivum.archgraph.mapper import knowledge_to_candidate_object, knowledge_to_candidate_relationship
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema


# ---------------------------------------------------------------------------
# Async pipeline runner
# ---------------------------------------------------------------------------

async def _run_ingest(repo: Path, scope: str, cache_dir: Path, update: bool) -> IngestReport:
    """Open canonical knowledge storage and run the ingest pipeline."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    knowledge_path = repo / ".archivum" / "knowledge.db"
    knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(knowledge_path) as knowledge_conn:
        await init_knowledge_schema(knowledge_conn)
        async with aiosqlite.connect(cache_dir / "index.db") as lexical_conn:
            report = await ingest_repo(
                repo,
                scope=scope,
                cache_dir=cache_dir,
                knowledge=KnowledgeRepository(knowledge_conn),
                lexical_conn=lexical_conn,
                update=update,
            )
    return report


async def _run_ingest_and_export(
    repo: Path, scope: str, cache_dir: Path, update: bool, export_dir: Path
) -> tuple[IngestReport, Path]:
    """Like _run_ingest but also runs the export pipeline and returns (report, json_path)."""
    from archivum.archgraph.export import export_graph

    cache_dir.mkdir(parents=True, exist_ok=True)
    knowledge_path = repo / ".archivum" / "knowledge.db"
    knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(knowledge_path) as knowledge_conn:
        await init_knowledge_schema(knowledge_conn)
        knowledge = KnowledgeRepository(knowledge_conn)
        async with aiosqlite.connect(cache_dir / "index.db") as lexical_conn:
            report = await ingest_repo(
                repo,
                scope=scope,
                cache_dir=cache_dir,
                knowledge=knowledge,
                lexical_conn=lexical_conn,
                update=update,
            )
        objects = await knowledge.list_objects(scope=scope)
        relationships = await knowledge.list_relationships(scope=scope)
    json_path, _ = export_graph(
        [
            *(knowledge_to_candidate_object(object_) for object_ in objects),
            *(knowledge_to_candidate_relationship(relationship) for relationship in relationships),
        ],
        export_dir,
    )
    return report, json_path


# ---------------------------------------------------------------------------
# git post-commit hook installer
# ---------------------------------------------------------------------------

def install_post_commit_hook(repo: Path) -> Path:
    """Write an executable .git/hooks/post-commit that runs ``archivum-archgraph ingest``.

    Idempotent — overwrites any existing post-commit hook.
    Creates ``.git/hooks/`` if it does not exist.
    """
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hooks_dir / "post-commit"
    abs_repo = repo.resolve()
    script = f'#!/bin/sh\narchivum-archgraph ingest "{abs_repo}" --update\n'
    hook_path.write_text(script)
    os.chmod(hook_path, 0o755)
    return hook_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Parse args and run the archgraph ingest pipeline.

    Returns 0 on success, 2 on bad/missing args, 1 on pipeline error.
    """
    parser = argparse.ArgumentParser(
        prog="archivum-archgraph",
        description="Archgraph repo ingest CLI",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    ingest_parser = subparsers.add_parser("ingest", help="Ingest a repository")
    ingest_parser.add_argument("repo_path", type=Path, help="Path to the repository root")
    ingest_parser.add_argument("--scope", default=None, help="Scope string (default: repo:<name>)")
    ingest_parser.add_argument("--update", action="store_true", help="Incremental update mode")
    ingest_parser.add_argument("--cache-dir", type=Path, default=None, dest="cache_dir", help="Cache directory")
    ingest_parser.add_argument("--export", type=Path, default=None, dest="export_dir", metavar="DIR", help="Export graph.json + graph.html to DIR")

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2

    repo = args.repo_path.resolve()
    scope = args.scope if args.scope is not None else f"repo:{repo.name}"
    cache_dir = args.cache_dir if args.cache_dir is not None else repo / ".archivum-cache"

    try:
        if args.export_dir is not None:
            report, json_path = asyncio.run(
                _run_ingest_and_export(repo, scope, cache_dir, args.update, args.export_dir)
            )
            print(f"archgraph: exported {json_path}")
        else:
            report = asyncio.run(_run_ingest(repo, scope, cache_dir, args.update))
    except Exception as exc:  # noqa: BLE001
        print(f"archgraph: error — {exc}", file=sys.stderr)
        return 1

    print(
        f"archgraph: ingested {repo} files={report.files} nodes={report.nodes} "
        f"edges={report.edges} (scope={scope})"
    )
    return 0
