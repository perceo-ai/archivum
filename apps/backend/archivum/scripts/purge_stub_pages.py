"""Remove the content-free code pages the pre-#71 indexer left behind.

Dry run by default: it prints what it would delete and why it would leave the
rest, and touches nothing. `--execute` removes exactly the pages the dry run
listed as matched — the vault file, the database row, and the page's search,
graph and knowledge entries — and nothing else.

    python -m archivum.scripts.purge_stub_pages --db-path /data/archivum.db
    python -m archivum.scripts.purge_stub_pages --db-path /data/archivum.db --execute

Run it with the same environment as the server, so `--wiki-dir` and the search
and graph settings resolve to the live vault rather than to defaults.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archivum.config import Settings, get_settings
from archivum.db import sqlite
from archivum.vault_scaffold import VAULT_MARKER

DEFAULT_PREFIX = "code/nixos"

# Exit codes. A purge that matched nothing, or removed less than it matched,
# must not look like one that did what it was asked.
EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_NOTHING_TO_PURGE = 2


@dataclass(frozen=True)
class PurgeReport:
    prefix: str
    wiki_id: str
    db_path: str
    wiki_dir: str
    mode: str
    outcome: str
    matched: list[str]
    skipped: list[dict[str, str]]
    deleted: list[str]
    degraded: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefix": self.prefix,
            "wiki_id": self.wiki_id,
            "db_path": self.db_path,
            "wiki_dir": self.wiki_dir,
            "mode": self.mode,
            "outcome": self.outcome,
            "counts": {
                "matched": len(self.matched),
                "skipped": len(self.skipped),
                "deleted": len(self.deleted),
            },
            "matched": self.matched,
            "skipped": self.skipped,
            "deleted": self.deleted,
            "degraded": self.degraded,
        }


async def _purge(args: argparse.Namespace, settings: Settings) -> PurgeReport:
    # Imported here: indexing pulls in the search and graph clients, which a
    # dry run has no reason to load.
    from archivum.indexing import forget_page

    degraded: dict[str, list[str]] = {}

    def file_text(slug: str) -> str | None:
        path = settings.wiki_dir / f"{slug}.md"
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None

    async def precheck(slug: str, checked: str) -> str | None:
        # The vault file is what a reconcile reads back, so it has the last
        # word. One that differs from the row is an edit the watcher has not
        # swept yet — the same test code_pages applies before retiring a page.
        text = file_text(slug)
        if text is not None and text != checked:
            return "vault file differs from the indexed row (an unswept edit); left in place"
        return None

    async def forget(slug: str, checked: str) -> str | None:
        # The row is gone. Anything that changed in the moment since is a
        # person's: leave it for reconcile to read back rather than remove it.
        text = file_text(slug)
        if text is not None and text != checked:
            return "vault file edited during the purge; kept for reconcile to read back"
        if await sqlite.get_page(slug, args.wiki_id) is not None:
            return "page saved again during the purge; kept"
        (settings.wiki_dir / f"{slug}.md").unlink(missing_ok=True)
        result = await forget_page(slug, wiki_id=args.wiki_id, settings=settings)
        if result.degraded:
            degraded[slug] = list(result.degraded)
        return None

    report = await sqlite.purge_stub_pages_under(
        args.prefix, args.wiki_id, dry_run=not args.execute, precheck=precheck, forget=forget
    )

    if not args.execute:
        outcome = "dry-run"
    elif not report["matched"]:
        outcome = "nothing-to-purge"
    elif len(report["deleted"]) < len(report["matched"]):
        outcome = "partial"
    else:
        outcome = "purged"

    return PurgeReport(
        prefix=report["prefix"],
        wiki_id=args.wiki_id,
        db_path=str(settings.db_path),
        wiki_dir=str(settings.wiki_dir),
        mode="execute" if args.execute else "dry-run",
        outcome=outcome,
        matched=report["matched"],
        skipped=report["skipped"],
        deleted=report["deleted"],
        degraded=degraded,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archivum-purge-stub-pages")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Folder under code/ to purge.")
    parser.add_argument("--wiki-id", default="default", help="Vault the pages belong to.")
    parser.add_argument("--db-path", help="SQLite file to read (default: the configured one).")
    parser.add_argument("--wiki-dir", help="Vault directory holding the .md files (default: configured).")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete. Without this the script only prints what it would do.",
    )
    args = parser.parse_args(argv)

    overrides: dict[str, Any] = {}
    if args.db_path:
        overrides["db_path"] = Path(args.db_path)
    if args.wiki_dir:
        overrides["wiki_dir"] = Path(args.wiki_dir)
    settings = get_settings().model_copy(update=overrides) if overrides else get_settings()

    # Opening a path that is not there would create an empty database and then
    # report, truthfully but uselessly, that it found nothing to purge.
    if not settings.db_path.is_file():
        raise SystemExit(f"No database at {settings.db_path}; pass --db-path to the live vault's file.")
    # Page paths carry no wiki id, so a directory belonging to another wiki
    # would have that wiki's files unlinked under this one's slugs.
    marker = settings.wiki_dir / VAULT_MARKER
    owner = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
    if owner and owner != args.wiki_id:
        raise SystemExit(f"{settings.wiki_dir} is the vault for wiki {owner!r}, not {args.wiki_id!r}.")
    # Without the vault directory the files stay, and reconcile reads every
    # purged stub straight back in.
    if args.execute and not settings.wiki_dir.is_dir():
        raise SystemExit(f"No vault directory at {settings.wiki_dir}; pass --wiki-dir to the live vault.")

    sqlite.configure(settings)
    try:
        report = asyncio.run(_purge(args, settings))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if report.outcome == "nothing-to-purge":
        return EXIT_NOTHING_TO_PURGE
    if report.outcome == "partial":
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
