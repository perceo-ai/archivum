"""One timestamp format for anything that gets sorted or compared.

SQLite column defaults use `datetime('now')`, which is space-separated, second
precision, and has no timezone. Application writes use `datetime.now(UTC).isoformat()`,
which is `T`-separated with microseconds and an offset. Both formats live in the
same columns across the schema.

That matters because the activity stream orders items lexicographically across
four different tables. Compared as strings, `' '` (0x20) sorts before `'T'`
(0x54), so *every* default-written row sorts before *every* application-written
row no matter what time it actually records. Normalising on read keeps the
ordering honest without a migration.
"""

from __future__ import annotations

from datetime import UTC, datetime


def normalise_timestamp(value: str | None) -> str:
    """Return an ISO-8601 UTC string, or "" if the value is unusable.

    Accepts both SQLite's `YYYY-MM-DD HH:MM:SS` and full ISO-8601 with or
    without an offset. Naive values are treated as UTC, which is what both
    writers intend.
    """
    if not value:
        return ""
    text = value.strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()
