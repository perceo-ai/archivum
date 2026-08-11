"""archgraph.hook — CLI entrypoint and git post-commit hook installer.

Stand-in design
---------------
PER-317's real ValidationLayer is not yet built.  ``_CollectingSink`` below is
a temporary stand-in that enforces the spec §4 invariant (every candidate must
carry ≥1 provenance link and a valid extraction_method) exactly as the real
ValidationLayer will — valid candidates go to ``self.accepted``, invalid ones to
``self.rejected``.  When PER-317 lands, swap ``_CollectingSink`` for the real
``ValidationLayer`` in ``_run_ingest``.

``_run_ingest`` also opens an ephemeral aiosqlite connection to
``<cache_dir>/index.db``; this is a placeholder DB used only by the lexical
index builder.  PER-317 will route this through the real persistence layer.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import aiosqlite

from archivum.archgraph.ingest import IngestReport, ingest_repo


# ---------------------------------------------------------------------------
# Stand-in validation sink (replace with real ValidationLayer when PER-317 lands)
# ---------------------------------------------------------------------------

_VALID_METHODS = frozenset({"EXTRACTED", "INFERRED", "AMBIGUOUS"})


class _CollectingSink:
    """Provenance-enforcing stand-in for PER-317's ValidationLayer.

    Mirrors the §4 invariant the real layer enforces: a candidate is accepted
    only if it has ≥1 provenance entry and an extraction_method in the enum.
    Anything else is recorded in ``self.rejected`` (never raised — a bad
    candidate must not abort the whole ingest).
    """

    def __init__(self) -> None:
        self.accepted: list[object] = []
        self.rejected: list[object] = []

    def validate_batch(self, candidates: list) -> None:
        for c in candidates:
            provenance = getattr(c, "provenance", None)
            method = getattr(c, "extraction_method", None)
            if provenance and method in _VALID_METHODS:
                self.accepted.append(c)
            else:
                self.rejected.append(c)


# ---------------------------------------------------------------------------
# Async pipeline runner
# ---------------------------------------------------------------------------

async def _run_ingest(repo: Path, scope: str, cache_dir: Path, update: bool) -> IngestReport:
    """Construct local sink + aiosqlite connection, run ingest_repo, return report."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    sink = _CollectingSink()
    async with aiosqlite.connect(cache_dir / "index.db") as conn:
        report = await ingest_repo(
            repo,
            scope=scope,
            cache_dir=cache_dir,
            validation=sink,
            lexical_conn=conn,
            update=update,
        )
    return report


async def _run_ingest_and_export(
    repo: Path, scope: str, cache_dir: Path, update: bool, export_dir: Path
) -> tuple[IngestReport, Path]:
    """Like _run_ingest but also runs the export pipeline and returns (report, json_path)."""
    from archivum.archgraph.export import export_graph

    cache_dir.mkdir(parents=True, exist_ok=True)
    sink = _CollectingSink()
    async with aiosqlite.connect(cache_dir / "index.db") as conn:
        report = await ingest_repo(
            repo,
            scope=scope,
            cache_dir=cache_dir,
            validation=sink,
            lexical_conn=conn,
            update=update,
        )
    json_path, _ = export_graph(sink.accepted, export_dir)
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
