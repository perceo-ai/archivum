"""The folders a new vault starts with.

An empty vault makes every capture a decision: where does this go? The composer
already guesses a folder, but it can only guess among folders that exist, so on
a fresh install it always guesses "the root" and everything piles up there.

These are a starting point, not a policy. They are created once, on a vault that
has no folders of its own. Delete one and it stays deleted; arrive with your own
structure and nothing is added — being handed a second organising scheme on top
of your own is worse than being handed none.

The names are deliberately about *what a thing is to you* rather than what
Archivum did to it. `code/`, `memory/` and `skills/` are written by the system
and are excluded from this list for that reason: they are output, not places you
put things.
"""

from __future__ import annotations

import logging

from archivum.config import Settings
from archivum.db import sqlite

logger = logging.getLogger(__name__)

# Ordered as they should read in a sidebar: the things you add to daily first,
# the reference material after.
DEFAULT_FOLDERS: tuple[str, ...] = (
    "inbox",
    "daily",
    "notes",
    "projects",
    "areas",
    "people",
    "decisions",
    "reading",
    "reference",
    "sources",
    "archive",
)

FOLDER_PURPOSE: dict[str, str] = {
    "inbox": "Anything captured before you decided where it goes.",
    "daily": "One note per day. `T` opens today's.",
    "notes": "Thinking that is not about one project.",
    "projects": "A page per thing you are actually building.",
    "areas": "Ongoing responsibilities rather than finite projects.",
    "people": "Who you work with, and what you know about them.",
    "decisions": "What you chose and why, so future-you can check the reasoning.",
    "reading": "Papers, posts and books, with what you took from them.",
    "reference": "Documentation and specs you come back to.",
    "sources": "Things you brought in from elsewhere.",
    "archive": "Done, but not deleted.",
}


async def ensure_default_folders(
    *, wiki_id: str, settings: Settings | None = None
) -> list[str]:
    """Create the starting folders on a vault that has none. Returns what it made.

    Deliberately all-or-nothing on the *first* run: if any folder already
    exists, the vault has a shape and this does not add to it. That is what
    keeps a deleted folder deleted, rather than having it reappear on every
    restart.
    """
    existing = {row["path"] for row in await sqlite.list_folders(wiki_id)}
    if existing:
        return []

    created: list[str] = []
    for path in DEFAULT_FOLDERS:
        try:
            await sqlite.create_folder(path, wiki_id)
            created.append(path)
        except Exception as exc:  # noqa: BLE001 - a folder is not worth a failed boot
            logger.warning("Could not create default folder %s: %s", path, exc)
    if created:
        logger.info("Created %d starting folders", len(created))
    return created
