"""Notice when the vault changes underneath the app.

You are meant to edit this vault by hand — in an editor, over a sync folder,
with `git pull`. None of those tell Archivum anything, so it has to look.

This polls modification times rather than subscribing to filesystem events.
Polling is unfashionable but it is the right trade here: inotify is unreliable
across bind mounts and network shares, misses whole-tree changes like a git
checkout, and needs a dependency. A stat-per-file sweep on a personal vault is
a few milliseconds, and it catches every one of those cases identically.

Only files whose mtime moved are reindexed, and `reindex_page` compares content
before writing, so a touched-but-unchanged file costs one read and nothing else.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from archivum.config import Settings
from archivum.db import sqlite
from archivum.indexing import ReindexResult, forget_page, reindex_page, slug_for_path

logger = logging.getLogger(__name__)


def scan_vault(settings: Settings) -> dict[str, float]:
    """Slug → mtime for every markdown file currently in the vault."""
    seen: dict[str, float] = {}
    if not settings.wiki_dir.exists():
        return seen
    for path in settings.wiki_dir.rglob("*.md"):
        slug = slug_for_path(settings, path)
        if not slug:
            continue
        try:
            seen[slug] = path.stat().st_mtime
        except OSError:
            # Vanished between listing and stat — the next sweep will settle it.
            continue
    return seen


def changed_slugs(
    previous: dict[str, float], current: dict[str, float]
) -> tuple[set[str], set[str]]:
    """(written, removed) since the last sweep."""
    written = {
        slug
        for slug, mtime in current.items()
        if slug not in previous or previous[slug] != mtime
    }
    removed = set(previous) - set(current)
    return written, removed


async def sweep_once(
    *,
    wiki_id: str,
    settings: Settings,
    previous: dict[str, float],
) -> tuple[dict[str, float], list[ReindexResult]]:
    """One pass. Returns the new snapshot and what it did."""
    current = scan_vault(settings)
    written, removed = changed_slugs(previous, current)
    results: list[ReindexResult] = []

    for slug in sorted(written):
        results.append(
            await reindex_page(
                slug, wiki_id=wiki_id, settings=settings, reason="vault-watch"
            )
        )

    for slug in sorted(removed):
        if await sqlite.get_page(slug, wiki_id) is None:
            continue
        result = ReindexResult(slug=slug, reason="vault-watch")
        await forget_page(slug, wiki_id=wiki_id, settings=settings, result=result)
        result.action = "removed"
        results.append(result)

    return current, results


async def run_vault_watcher(settings: Settings, *, wiki_id: str = "default") -> None:
    """Watch the vault for the lifetime of the process."""
    interval = max(settings.vault_watch_interval_seconds, 1)
    logger.info(
        "Watching vault for external edits",
        extra={"wiki_dir": str(settings.wiki_dir), "interval_s": interval},
    )
    # Seed from what is already indexed so startup does not reindex the world;
    # the reconcile pass at startup has already settled any drift.
    snapshot = scan_vault(settings)

    while True:
        try:
            await asyncio.sleep(interval)
            snapshot, results = await sweep_once(
                wiki_id=wiki_id, settings=settings, previous=snapshot
            )
            touched = [r for r in results if r.action != "unchanged"]
            if touched:
                logger.info(
                    "Vault watcher indexed %d change(s): %s",
                    len(touched),
                    ", ".join(f"{r.slug} ({r.action})" for r in touched[:5]),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a bad sweep must not kill the watcher
            logger.warning("Vault watch sweep failed: %s", exc)
